"""
Bot Controller: Orchestrates Telegram user requests, multi-patient state retrieval,
7-Node LangGraph cycle execution, and grounded clinical dialogue generation.
"""

import re
from typing import Any, Dict, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from ..storage.database import get_db_session_manager, DatabaseSessionManager
from ..storage.seed import seed_database
from ..storage.postgres_saver import PostgresSaver
from ..storage.repositories import (
    CarePlanRepository,
    PredictionRepository,
    ScheduleRepository,
    FeedbackRepository,
    AgentActionRepository,
    ConversationRepository,
)
from ..orchestrator import MultiPatientOrchestrator
from ..adapters.hospital_adapter import HospitalEventAdapter
from ..scheduling.monitoring_scheduler import MonitoringScheduler
from ..config.llm_config import get_llms_pool
from ..views.telegram_view import TelegramView
from ..views.console_view import ConsoleTraceView, safe_console_print


def sanitize_text(text: str) -> str:
    """Strips internal reasoning <think>...</think> tags and Unicode smart quotes."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    replacements = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2011": "-", "\u2026": "...",
        "\u00a0": " ",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.strip()


class BotController:
    """
    Controller coordinating all business logic for the Telegram Post-Care Nurse Assistant.
    """

    def __init__(self, db_manager: Optional[DatabaseSessionManager] = None):
        self.db = db_manager or get_db_session_manager()

        # Ensure database is seeded with 10 longitudinal patients
        with self.db.session_scope() as session:
            seed_database(session)

        # Core Agentic Components
        self.checkpointer = PostgresSaver(db_manager=self.db)
        self.orchestrator = MultiPatientOrchestrator(checkpointer=self.checkpointer)
        self.scheduler = MonitoringScheduler(db_manager=self.db)
        self.adapter = HospitalEventAdapter(
            orchestrator=self.orchestrator,
            db_manager=self.db,
            scheduler=self.scheduler,
        )

        # LLM Pool for grounded natural language synthesis
        self.llm_pool = get_llms_pool(temperature=0.3)

        # Chat session registry
        self.chat_patients: Dict[int, str] = {}
        self.sessions: Dict[int, list] = {}

    def get_patient_for_chat(self, chat_id: int) -> str:
        """Returns the active patient ID for a given Telegram chat (default: P001)."""
        return self.chat_patients.get(chat_id, "P001")

    def set_patient_for_chat(self, chat_id: int, patient_id: str) -> str:
        """Switches active patient ID and resets chat memory for the session."""
        clean_pid = patient_id.strip().upper()
        self.chat_patients[chat_id] = clean_pid
        self.ensure_patient_activated(clean_pid)
        self.sessions.pop(chat_id, None)
        return clean_pid

    def ensure_patient_activated(self, patient_id: str):
        """Ensures patient is enrolled in the orchestrator state machine."""
        st = self.orchestrator.get_patient_state(patient_id)
        if not st:
            with self.db.session_scope() as session:
                plan_repo = CarePlanRepository(session)
                active_plan = plan_repo.get_active_care_plan(patient_id)
                if active_plan:
                    self.orchestrator.register_patient(
                        patient_id=patient_id,
                        risk_score=active_plan.plan_data.get("risk_score", 0.5) if active_plan.plan_data else 0.5,
                        risk_level=active_plan.plan_data.get("risk_level", "MEDIUM") if active_plan.plan_data else "MEDIUM",
                        care_duration_days=active_plan.duration_days,
                        clinical_notes=active_plan.plan_data.get("diagnosis", "Enrolled in Post-Care"),
                    )
                else:
                    self.adapter.process_hospital_event({
                        "patient_id": patient_id,
                        "event_type": "PATIENT_DISCHARGED",
                        "hospital_id": "METRO_GEN",
                    })

    def get_morning_greeting(self, chat_id: int, user_name: str = "Patient") -> str:
        """Generates a personalized clinical morning check-in outreach based on patient's current day and surgery."""
        patient_id = self.get_patient_for_chat(chat_id)
        self.ensure_patient_activated(patient_id)
        st = self.orchestrator.get_patient_state(patient_id) or {}

        curr_day = (st.get("current_day", 3)) + 1
        care_duration = st.get("care_duration_days", 30)
        risk_level = st.get("risk_level", "MEDIUM")

        with self.db.session_scope() as session:
            plan_repo = CarePlanRepository(session)
            plan = plan_repo.get_active_care_plan(patient_id)
            diagnosis = plan.plan_data.get("diagnosis", "your surgery") if (plan and plan.plan_data) else "your surgery"
            p_name = plan.plan_data.get("patient_name", user_name) if (plan and plan.plan_data) else user_name

        greeting_prompt = f"""You are 'Nurse Elena', an expert hospital recovery clinician.
You are initiating the morning recovery check-in for Patient {patient_id} ({p_name}) on Day {curr_day} of their {care_duration}-day recovery plan.
Patient Condition: {diagnosis} (Baseline Risk Tier: {risk_level}).

TASK:
Write a warm, polite morning check-in greeting (2 sentences max).
1. Greet them by name ({p_name}) for Day {curr_day}.
2. Inquire gently about their rest/sleep, how they are feeling regarding their {diagnosis}, and if they have taken their morning medications.
Keep it natural, warm, and clinical."""

        reply = None
        for candidate in self.llm_pool:
            try:
                response = candidate.invoke([SystemMessage(content=greeting_prompt)]).content.strip()
                if response:
                    reply = sanitize_text(response)
                    break
            except Exception:
                continue

        if not reply:
            reply = (
                f"Good morning {p_name}! ☀️ It's Nurse Elena checking in for Day {curr_day} of your recovery from {diagnosis}.\n\n"
                f"How did you sleep last night, how are you feeling today, and have you taken your morning medications?"
            )

        # Save to database
        self.save_conversation(chat_id, "assistant", reply, patient_id)
        return reply


    def process_incoming_message(self, chat_id: int, user_text: str) -> str:
        """
        Executes a full 7-node LangGraph cycle and returns a grounded AI nurse reply.
        """
        patient_id = self.get_patient_for_chat(chat_id)
        self.ensure_patient_activated(patient_id)

        # 1. Ingest event through HospitalEventAdapter -> MultiPatientOrchestrator -> 7-Node LangGraph
        event_result = self.adapter.process_hospital_event({
            "patient_id": patient_id,
            "event_type": "DAILY_CHECKIN",
            "payload": {
                "symptoms": user_text,
                "text": user_text,
                "notes": f"Telegram session from chat_id {chat_id}",
            },
        })

        patient_state = event_result.get("patient_state", {})
        curr_day = patient_state.get("current_day", 1)
        care_duration = patient_state.get("care_duration_days", 30)
        risk_level = patient_state.get("risk_level", "MEDIUM")
        risk_score = patient_state.get("current_risk_score", 0.5)
        extracted_symptoms = patient_state.get("symptoms", [])
        med_adherence = patient_state.get("medication_adherence", 1.0)
        current_action = patient_state.get("current_action", "CONTINUE")
        monitoring_freq = patient_state.get("monitoring_frequency", "DAILY")
        escalation_req = patient_state.get("escalation_required", False)
        adaptation_notes = patient_state.get("adaptation_notes", [])
        latest_decision = adaptation_notes[-1] if adaptation_notes else "Routine check-in evaluated."
        next_sched = event_result.get("next_checkin_scheduled")

        # 2. Render Live Agentic Console Trace
        ConsoleTraceView.print_agentic_trace(
            patient_id=patient_id,
            current_day=curr_day,
            care_duration=care_duration,
            symptoms=extracted_symptoms,
            medication_adherence=med_adherence,
            risk_score=risk_score,
            risk_level=risk_level,
            current_action=current_action,
            monitoring_frequency=monitoring_freq,
            clinical_note=latest_decision,
            escalation_required=escalation_req,
            next_schedule=next_sched,
        )

        # 3. Natural Bedside Clinical Dialogue Generation
        with self.db.session_scope() as session:
            plan_repo = CarePlanRepository(session)
            plan = plan_repo.get_active_care_plan(patient_id)
            diagnosis = plan.plan_data.get("diagnosis", "your surgery") if (plan and plan.plan_data) else "your surgery"
            p_name = plan.plan_data.get("patient_name", "there") if (plan and plan.plan_data) else "there"
            prescribed_meds = plan.plan_data.get("prescribed_medications", []) if (plan and plan.plan_data) else []

        if prescribed_meds:
            med_list_desc = "\n".join([f"  • {m['name']} ({m['dose']}) - {m['frequency']} [Purpose: {m['purpose']}]" for m in prescribed_meds])
        else:
            med_list_desc = "  • Standard post-operative prescriptions"

        nurse_prompt = f"""You are 'Nurse Elena', an expert hospital bedside recovery clinician chatting live with Patient {patient_id} ({p_name}) on Day {curr_day} of their {care_duration}-day recovery from {diagnosis}.

PATIENT DISCHARGE PRESCRIPTION RECORD (FROM POSTGRESQL EHR):
{med_list_desc}

AGENT CLINICAL EVALUATION (BACKGROUND REASONING):
- Current Patient Message: "{user_text}"
- Active Extracted Symptoms: {extracted_symptoms if extracted_symptoms else 'None (stable/improving)'}
- Cumulative Medication Adherence: {med_adherence*100:.0f}%
- Agent Policy Decision: {current_action}
- Monitoring Cadence: {monitoring_freq}
- Urgent Escalation Required: {escalation_req}
- Clinical Reasoning: {latest_decision}

NATURAL CLINICAL CONVERSATION RULES:
1. Speak in a completely natural, warm, empathetic bedside clinician tone. Sound like a real caring human nurse.
2. Directly address what the patient just shared without repeating yourself.
3. You ALREADY KNOW their exact discharge medications from the list above. NEVER ask the patient "What medication are you taking?" or "What dose?". Instead, refer to them specifically by name and dose (e.g. "Did you take your morning {prescribed_meds[0]['name'] if prescribed_meds else 'pills'} as scheduled?").
4. If they already said they took their medication, simply acknowledge and move on—do NOT re-ask about medication.
5. Provide practical, comforting clinical advice tailored to {diagnosis} (e.g. hugging a pillow against the sternum when coughing, elevating swollen limbs, staying hydrated).
6. If the agent triggered 'ESCALATE' (chest tightness, severe shortness of breath), advise urgent clinician or emergency contact immediately.
7. Keep each response concise (2-3 sentences), warm, and human."""


        # Maintain session dialogue memory
        if chat_id not in self.sessions:
            self.sessions[chat_id] = []
            with self.db.session_scope() as session:
                c_repo = ConversationRepository(session)
                hist = c_repo.get_conversation_history(patient_id, limit=6)
                for m in hist:
                    if m.role == "patient":
                        self.sessions[chat_id].append(HumanMessage(content=m.message_text))
                    elif m.role == "assistant":
                        self.sessions[chat_id].append(AIMessage(content=m.message_text))

        history = self.sessions[chat_id]
        history.append(HumanMessage(content=user_text))

        # Track turn count for this session
        if not hasattr(self, "session_turns"):
            self.session_turns = {}
        current_turns = self.session_turns.get(chat_id, 0) + 1
        self.session_turns[chat_id] = current_turns

        # Check if conversation reached conclusion (5-7 turns or user says done/thanks)
        clean_msg = re.sub(r"[^\w\s]", "", user_text.lower()).strip()
        user_wants_closing = clean_msg in ["thanks", "thank you", "done", "bye", "goodbye", "all good", "okay thanks", "ok thanks", "im done", "i am done"]
        is_session_complete = (current_turns >= 5) or user_wants_closing

        if is_session_complete:
            nurse_prompt += f"\n\nNOTE: This check-in turn concludes the Day {curr_day} evaluation. Give a warm, encouraging closing sentence stating that you have recorded their check-in and are attaching their personalized daily care guidance below."

        reply = None
        for candidate in self.llm_pool:
            try:
                response = candidate.invoke([SystemMessage(content=nurse_prompt)] + history[-6:]).content.strip()
                if response:
                    reply = sanitize_text(response)
                    break
            except Exception:
                continue

        if not reply:
            if escalation_req:
                reply = (
                    f"Thank you for letting me know. Because of the symptoms you reported (Day {curr_day}), "
                    f"I have alerted our on-call clinical team for urgent review. Please contact emergency services or "
                    f"your doctor immediately if your symptoms worsen."
                )
            else:
                reply = (
                    f"Thank you for sharing your update for Day {curr_day}! I have logged your vitals and recovery status into your "
                    f"plan. Keep resting well, take your medications as prescribed, and follow your daily care guidance!"
                )

        history.append(AIMessage(content=reply))

        # Save both messages into PostgreSQL
        self.save_conversation(chat_id, "patient", user_text, patient_id)
        self.save_conversation(chat_id, "assistant", reply, patient_id)

        # If session reached 5-7 turns or user concluded, attach personalized Day Care Summary Card!
        if is_session_complete:
            self.session_turns[chat_id] = 0  # Reset for next session
            daily_care_card = self.generate_daily_care_card(patient_id, curr_day, p_name, diagnosis, prescribed_meds, next_sched)
            return reply + "\n\n" + daily_care_card

        return reply

    def generate_daily_care_card(
        self,
        patient_id: str,
        curr_day: int,
        p_name: str,
        diagnosis: str,
        prescribed_meds: List[Dict[str, Any]],
        next_sched: Optional[Dict[str, Any]],
    ) -> str:
        """Generates clinical nutrition, activity, and wound care guidance tailored to surgery and risk level."""
        diag_lower = diagnosis.lower()
        if "cabg" in diag_lower or "bypass" in diag_lower or "cardiac" in diag_lower or "heart" in diag_lower:
            nutrition = "Heart-healthy diet: Low-sodium (<2000mg/day), lean proteins, leafy greens, and drink 6-8 glasses of water."
            activity = "Walk 10-15 minutes at a relaxed pace inside the house 2-3 times today. Avoid lifting anything > 5 lbs."
            wound_care = "Keep chest and leg incision dry. Hug a firm pillow against your chest whenever you need to cough or sneeze."
        elif "knee" in diag_lower or "arthroplasty" in diag_lower:
            nutrition = "High-protein recovery meals with calcium and vitamin D to support joint and tissue repair. Stay well-hydrated."
            activity = "Perform your physical therapy ankle pumps and quad sets 3 times today. Walk with your walker/crutches as tolerated."
            wound_care = "Elevate leg above heart level when resting. Ice knee for 20 minutes at a time to keep swelling down."
        elif "copd" in diag_lower or "lung" in diag_lower or "pneumonia" in diag_lower:
            nutrition = "Eat small, frequent, nutrient-dense meals to avoid diaphragm pressure. Drink warm fluids to thin mucus."
            activity = "Gentle breathing exercises: Pursed-lip breathing and short sitting walks. Keep pulse oximeter nearby."
            wound_care = "Rest in a comfortable semi-upright position. Stay in clean, well-ventilated, smoke-free air."
        elif "colectomy" in diag_lower or "bowel" in diag_lower or "append" in diag_lower:
            nutrition = "Soft, low-fiber, easily digestible foods (soups, oatmeal, bananas, broths). Avoid heavy spices and carbonated drinks."
            activity = "Light walking around living room to stimulate gentle bowel motility. No strenuous abdominal bending."
            wound_care = "Inspect incision for any increased redness or warmth. Keep dressings clean and dry."
        elif "spinal" in diag_lower or "fusion" in diag_lower or "spine" in diag_lower:
            nutrition = "Anti-inflammatory meals rich in magnesium, fiber, and plenty of fluids to prevent medication-related constipation."
            activity = "Wear prescribed back brace when out of bed. Strict BLT rules: No Bending, No Lifting (>5 lbs), No Twisting."
            wound_care = "Keep surgical dressing clean and intact. Log-roll when getting in and out of bed."
        else:
            nutrition = "Balanced post-operative diet rich in lean protein, vitamin C, and adequate hydration to accelerate tissue healing."
            activity = "Short gentle walks throughout the day. Rest whenever you feel fatigued."
            wound_care = "Keep surgical incisions clean, dry, and protected. Avoid submerging in baths."

        next_txt = f"Day {curr_day + 1} morning at 09:00 AM" if not next_sched else f"Day {next_sched.get('care_day')} ({next_sched.get('monitoring_frequency')}) at {next_sched.get('scheduled_at')}"

        return TelegramView.format_daily_care_summary(
            patient_id=patient_id,
            patient_name=p_name,
            current_day=curr_day,
            diagnosis=diagnosis,
            prescribed_medications=prescribed_meds,
            nutrition_guidelines=nutrition,
            activity_target=activity,
            wound_care=wound_care,
            next_checkin_text=next_txt,
        )


    def get_status_view(self, chat_id: int) -> str:
        """Retrieves and formats status card using TelegramView."""
        patient_id = self.get_patient_for_chat(chat_id)
        self.ensure_patient_activated(patient_id)
        st = self.orchestrator.get_patient_state(patient_id) or {}

        curr_day = st.get("current_day", 1)
        care_duration = st.get("care_duration_days", 30)
        risk_level = st.get("risk_level", "MEDIUM")
        risk_score = st.get("current_risk_score", 0.5)
        symptoms = st.get("symptoms", [])
        adherence = st.get("medication_adherence", 1.0)
        freq = st.get("monitoring_frequency", "DAILY")
        action = st.get("current_action", "CONTINUE")
        status = st.get("plan_status", "ACTIVE")
        notes = st.get("adaptation_notes", ["Baseline monitoring active."])[-1] if st.get("adaptation_notes") else "None"

        with self.db.session_scope() as session:
            s_repo = ScheduleRepository(session)
            pend = s_repo.get_pending_schedules(patient_id)
            next_sched_txt = (
                f"Day {pend[0].care_day} ({pend[0].frequency}) at {pend[0].scheduled_at.strftime('%Y-%m-%d %H:%M UTC')}"
                if pend else "No pending check-ins"
            )

        return TelegramView.format_status_card(
            patient_id=patient_id,
            current_day=curr_day,
            care_duration=care_duration,
            plan_status=status,
            risk_level=risk_level,
            risk_score=risk_score,
            symptoms=symptoms,
            medication_adherence=adherence,
            monitoring_frequency=freq,
            current_action=action,
            clinical_note=notes,
            next_checkin_text=next_sched_txt,
        )

    def get_history_view(self, chat_id: int) -> str:
        """Retrieves and formats longitudinal history using TelegramView."""
        patient_id = self.get_patient_for_chat(chat_id)
        with self.db.session_scope() as session:
            f_repo = FeedbackRepository(session)
            a_repo = AgentActionRepository(session)
            feedbacks = f_repo.get_feedback_history(patient_id)
            actions = a_repo.get_patient_actions(patient_id)
            action_by_day = {a.day: a.action_type for a in actions}

        return TelegramView.format_history_summary(
            patient_id=patient_id,
            feedbacks=feedbacks,
            actions_by_day=action_by_day,
        )

    def get_care_plan_view(self, chat_id: int) -> str:
        """Retrieves and formats care plan details using TelegramView."""
        patient_id = self.get_patient_for_chat(chat_id)
        with self.db.session_scope() as session:
            plan_repo = CarePlanRepository(session)
            pred_repo = PredictionRepository(session)
            plan = plan_repo.get_active_care_plan(patient_id)
            pred = pred_repo.get_latest_prediction(patient_id)

            if not plan:
                return f"No active care plan found for patient `{patient_id}`."

            diagnosis = plan.plan_data.get("diagnosis", "Post-Op Recovery") if plan.plan_data else "Post-Op Recovery"
            p_name = plan.plan_data.get("patient_name", "Patient") if plan.plan_data else "Patient"
            prescribed_meds = plan.plan_data.get("prescribed_medications", []) if plan.plan_data else []

            return TelegramView.format_care_plan(
                patient_id=patient_id,
                patient_name=p_name,
                diagnosis=diagnosis,
                status=plan.status,
                duration_days=plan.duration_days,
                current_day=plan.current_day,
                monitoring_frequency=plan.monitoring_frequency,
                risk_level=pred.risk_level if pred else "N/A",
                risk_score=pred.risk_score if pred else 0.0,
                prescribed_medications=prescribed_meds,
            )

    def save_conversation(self, chat_id: int, role: str, text: str, patient_id: str):
        """Persists chat message to PostgreSQL patient_conversations table."""
        try:
            with self.db.session_scope() as session:
                repo = ConversationRepository(session)
                repo.save_message(
                    chat_id=str(chat_id),
                    role=role,
                    message_text=text,
                    patient_id=patient_id,
                    channel="TELEGRAM",
                )
        except Exception as e:
            safe_console_print(f"[DB Save Error]: {e}")
