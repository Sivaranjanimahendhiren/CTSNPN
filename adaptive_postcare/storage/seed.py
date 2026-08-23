"""
Comprehensive Longitudinal Seed Dataset Generator for PostgreSQL Storage Layer.
Seeds 10 realistic patient clinical profiles with day-by-day historical records & discharge prescriptions:
- Specific prescribed medications with doses, frequencies, and clinical purposes
- Day-by-day hospital events (PATIENT_DISCHARGED, DAILY_CHECKIN for Day 1, Day 2, Day 3, etc.)
- Day-by-day multi-turn Telegram conversations in patient_conversations
- Day-by-day structured clinical extractions in patient_feedback
- Day-by-day executed agent tool actions in agent_actions
- Completed and pending check-in schedules in monitoring_schedules
- Initialized LangGraph checkpoints in langgraph_checkpoints via PostgresSaver (thread_id = patient_id)
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List
import json
from sqlalchemy.orm import Session
from .database import get_db_session_manager
from .repositories import (
    PatientRepository,
    HospitalRepository,
    PredictionRepository,
    EventRepository,
    PatientProfileRepository,
    CarePlanRepository,
    FeedbackRepository,
    AgentActionRepository,
    ScheduleRepository,
    ConversationRepository,
)
from .postgres_saver import PostgresSaver

SYNTHETIC_HOSPITALS = [
    {
        "hospital_id": "HOSP-001",
        "hospital_code": "METRO_GEN",
        "hospital_name": "Metro General Hospital",
        "location": "New York, NY",
        "is_active": True,
    },
    {
        "hospital_id": "HOSP-002",
        "hospital_code": "ST_JUDE",
        "hospital_name": "St. Jude Memorial Hospital",
        "location": "Boston, MA",
        "is_active": True,
    },
    {
        "hospital_id": "HOSP-003",
        "hospital_code": "CITY_CARDIO",
        "hospital_name": "City Heart & Cardiology Center",
        "location": "Chicago, IL",
        "is_active": True,
    },
]

# 10 Detailed Longitudinal Clinical Profiles with Prescribed Discharge Medications
PATIENT_SEEDS = [
    {
        "patient_id": "P001",
        "hospital_id": "HOSP-001",
        "name": "John Doe",
        "age": 62,
        "gender": "Male",
        "diagnosis": "Coronary Artery Bypass Graft (CABG x3)",
        "risk_score": 0.78,
        "risk_level": "HIGH",
        "care_duration_days": 30,
        "monitoring_frequency": "DAILY",
        "completed_days": 3,
        "current_day": 3,
        "prescribed_medications": [
            {"name": "Aspirin", "dose": "81mg", "frequency": "Daily with breakfast", "purpose": "Antiplatelet blood thinner to protect new bypass grafts"},
            {"name": "Metoprolol Succinate", "dose": "25mg", "frequency": "Twice daily (Morning & Evening)", "purpose": "Beta-blocker for blood pressure and heart rate control"},
            {"name": "Atorvastatin", "dose": "40mg", "frequency": "Once nightly at bedtime", "purpose": "Cholesterol reduction and arterial plaque stabilization"},
        ],
        "daily_history": [
            {
                "day": 1,
                "symptoms": ["sternal incisional soreness (4/10)"],
                "meds_taken": True,
                "pain": 4,
                "action": "CONTINUE",
                "patient_msg": "Good morning Elena. Soreness around my sternum is about a 4/10, but I took all my morning blood pressure and aspirin pills.",
                "nurse_reply": "Good morning John! Incisional soreness of 4/10 is expected on Day 1. Remember to hug a pillow when coughing to protect your sternum. I have logged your 100% medication adherence!",
            },
            {
                "day": 2,
                "symptoms": ["mild sternal tenderness (2/10)"],
                "meds_taken": True,
                "pain": 2,
                "action": "CONTINUE",
                "patient_msg": "Feeling much better today! Sternal soreness dropped to a 2/10. Walked 10 minutes around the living room and took all meds.",
                "nurse_reply": "Excellent progress, John! Walking 10 minutes is great for your circulation. Keep up the consistent medication schedule. Rest well today!",
            },
            {
                "day": 3,
                "symptoms": [],
                "meds_taken": True,
                "pain": 1,
                "action": "CONTINUE",
                "patient_msg": "Slept 8 hours last night. No chest discomfort, energy is good, took morning pills with breakfast.",
                "nurse_reply": "Wonderful update for Day 3, John! Your recovery trajectory is very stable. I have scheduled our next check-in for tomorrow morning.",
            },
        ],
    },
    {
        "patient_id": "P002",
        "hospital_id": "HOSP-002",
        "name": "Sarah Connor",
        "age": 48,
        "gender": "Female",
        "diagnosis": "Total Knee Arthroplasty (Right)",
        "risk_score": 0.45,
        "risk_level": "MEDIUM",
        "care_duration_days": 20,
        "monitoring_frequency": "DAILY",
        "completed_days": 2,
        "current_day": 2,
        "prescribed_medications": [
            {"name": "Eliquis (Apixaban)", "dose": "2.5mg", "frequency": "Twice daily", "purpose": "DVT blood clot prevention following joint replacement"},
            {"name": "Celecoxib (Celebrex)", "dose": "200mg", "frequency": "Once daily with food", "purpose": "NSAID for surgical knee inflammation and pain"},
            {"name": "Acetaminophen", "dose": "500mg", "frequency": "Every 6 hours as needed (Max 3000mg/day)", "purpose": "Mild-to-moderate baseline pain relief"},
        ],
        "daily_history": [
            {
                "day": 1,
                "symptoms": ["moderate knee swelling", "stiffness (5/10)"],
                "meds_taken": True,
                "pain": 5,
                "action": "CONTINUE",
                "patient_msg": "Hi Nurse Elena. My right knee is quite stiff and swollen today, pain around 5/10. Ice pack helps. Took blood thinners and pain medication.",
                "nurse_reply": "Hello Sarah! Post-operative swelling is normal on Day 1. Keep the leg elevated above heart level and ice for 20 minutes at a time. Glad you took your blood thinner!",
            },
            {
                "day": 2,
                "symptoms": ["mild knee stiffness (3/10)"],
                "meds_taken": True,
                "pain": 3,
                "action": "CONTINUE",
                "patient_msg": "Swelling has gone down a bit and did my ankle pumps. Pain is down to 3/10. All meds taken on schedule.",
                "nurse_reply": "Great job on completing your physical therapy ankle pumps, Sarah! Reducing swelling and maintaining 100% adherence is key. Keep up the great work!",
            },
        ],
    },
    {
        "patient_id": "P003",
        "hospital_id": "HOSP-001",
        "name": "Robert Smith",
        "age": 71,
        "gender": "Male",
        "diagnosis": "COPD Exacerbation & Bronchitis",
        "risk_score": 0.82,
        "risk_level": "HIGH",
        "care_duration_days": 30,
        "monitoring_frequency": "DAILY",
        "completed_days": 3,
        "current_day": 3,
        "prescribed_medications": [
            {"name": "Symbicort (Budesonide/Formoterol)", "dose": "160/4.5 mcg", "frequency": "2 puffs Twice daily (Rinse mouth after)", "purpose": "Maintenance bronchodilator and inhaled corticosteroid"},
            {"name": "Albuterol HFA Inhaler", "dose": "90 mcg", "frequency": "2 puffs every 4-6 hours as needed", "purpose": "Rescue inhaler for sudden acute shortness of breath"},
            {"name": "Prednisone", "dose": "20mg", "frequency": "1 tablet Daily morning with food", "purpose": "Oral steroid taper to resolve lung airway inflammation"},
        ],
        "daily_history": [
            {
                "day": 1,
                "symptoms": ["morning wheezing", "dry cough"],
                "meds_taken": True,
                "pain": 0,
                "action": "CONTINUE",
                "patient_msg": "Morning Elena. Had a bit of wheezing when I woke up, but used my nebulizer and took my steroid pills.",
                "nurse_reply": "Hello Robert. Good to hear the nebulizer relieved the wheezing. Please monitor your oxygen saturation with your pulse oximeter today.",
            },
            {
                "day": 2,
                "symptoms": ["mild cough"],
                "meds_taken": True,
                "pain": 0,
                "action": "CONTINUE",
                "patient_msg": "Oxygen is at 96% today. Breathing is steady, just a mild cough. Inhalers and morning pills taken.",
                "nurse_reply": "96% oxygen is a great reading for your COPD baseline, Robert! Stay in a comfortable air-conditioned room and stay well-hydrated.",
            },
            {
                "day": 3,
                "symptoms": ["occasional clearing throat"],
                "meds_taken": True,
                "pain": 0,
                "action": "CONTINUE",
                "patient_msg": "Feeling stable today. Breathing comfortably while resting. All prescriptions taken on time.",
                "nurse_reply": "Very glad to hear that, Robert! Your respiratory stability is on track. I will check in with you tomorrow morning.",
            },
        ],
    },
    {
        "patient_id": "P004",
        "hospital_id": "HOSP-003",
        "name": "Emily Davis",
        "age": 35,
        "gender": "Female",
        "diagnosis": "Laparoscopic Appendectomy",
        "risk_score": 0.18,
        "risk_level": "LOW",
        "care_duration_days": 10,
        "monitoring_frequency": "DAILY",
        "completed_days": 2,
        "current_day": 2,
        "prescribed_medications": [
            {"name": "Ibuprofen", "dose": "400mg", "frequency": "Every 6-8 hours with food as needed", "purpose": "Pain and incision inflammation control"},
            {"name": "Acetaminophen", "dose": "500mg", "frequency": "Every 6 hours as needed", "purpose": "Mild pain relief"},
        ],
        "daily_history": [
            {
                "day": 1,
                "symptoms": ["mild port site tenderness (3/10)"],
                "meds_taken": True,
                "pain": 3,
                "action": "CONTINUE",
                "patient_msg": "Hi Elena, incisions look clean. Mild soreness when getting out of bed. Took Tylenol as needed.",
                "nurse_reply": "Hi Emily! Laparoscopic port sites heal quickly. Keep the incisions dry and clean. You're doing great on Day 1!",
            },
            {
                "day": 2,
                "symptoms": [],
                "meds_taken": True,
                "pain": 1,
                "action": "CONTINUE",
                "patient_msg": "Appetite is completely back, walked outside a bit. Barely any soreness left.",
                "nurse_reply": "Awesome recovery, Emily! Being low risk, your trajectory is ideal. Let me know if anything changes.",
            },
        ],
    },
    {
        "patient_id": "P005",
        "hospital_id": "HOSP-002",
        "name": "Michael Brown",
        "age": 58,
        "gender": "Male",
        "diagnosis": "Partial Colectomy for Diverticular Disease",
        "risk_score": 0.72,
        "risk_level": "HIGH",
        "care_duration_days": 20,
        "monitoring_frequency": "DAILY",
        "completed_days": 2,
        "current_day": 2,
        "prescribed_medications": [
            {"name": "Ciprofloxacin", "dose": "500mg", "frequency": "Twice daily with full glass of water", "purpose": "Antibiotic to prevent post-surgical intra-abdominal infection"},
            {"name": "Metronidazole (Flagyl)", "dose": "500mg", "frequency": "Twice daily with meals", "purpose": "Anaerobic antibiotic coverage"},
            {"name": "Docusate Sodium (Colace)", "dose": "100mg", "frequency": "Once nightly", "purpose": "Stool softener to prevent straining post-bowel resection"},
        ],
        "daily_history": [
            {
                "day": 1,
                "symptoms": ["mild abdominal soreness (3/10)"],
                "meds_taken": True,
                "pain": 3,
                "action": "CONTINUE",
                "patient_msg": "Incision clean, tolerating clear liquids and light soup. Took antibiotics and pain med.",
                "nurse_reply": "Good morning Michael! Tolerating soft foods is an encouraging milestone after abdominal surgery. Stay hydrated and take small sips.",
            },
            {
                "day": 2,
                "symptoms": ["mild abdominal distension", "pain (4/10)"],
                "meds_taken": True,
                "pain": 4,
                "action": "CONTINUE",
                "patient_msg": "Felt a little bloated after lunch and pain is around 4/10. Took all prescribed morning pills.",
                "nurse_reply": "Thank you for noting the bloating, Michael. We will watch that closely. Please avoid heavy foods, and notify me if pain rises further.",
            },
        ],
    },
    {
        "patient_id": "P006",
        "hospital_id": "HOSP-001",
        "name": "Linda White",
        "age": 66,
        "gender": "Female",
        "diagnosis": "Congestive Heart Failure (NYHA Class II)",
        "risk_score": 0.85,
        "risk_level": "HIGH",
        "care_duration_days": 30,
        "monitoring_frequency": "DAILY",
        "completed_days": 3,
        "current_day": 3,
        "prescribed_medications": [
            {"name": "Furosemide (Lasix)", "dose": "40mg", "frequency": "Once daily in the morning", "purpose": "Loop diuretic to eliminate excess fluid and prevent lung congestion"},
            {"name": "Potassium Chloride", "dose": "20 mEq", "frequency": "Once daily with breakfast", "purpose": "Electrolyte replacement paired with Lasix"},
            {"name": "Carvedilol (Coreg)", "dose": "6.25mg", "frequency": "Twice daily with meals", "purpose": "Beta-blocker to support left ventricular cardiac function"},
            {"name": "Lisinopril", "dose": "10mg", "frequency": "Once daily in morning", "purpose": "ACE inhibitor to reduce cardiac afterload and protect kidneys"},
        ],
        "daily_history": [
            {
                "day": 1,
                "symptoms": ["mild ankle edema (1+)"],
                "meds_taken": True,
                "pain": 0,
                "action": "CONTINUE",
                "patient_msg": "Morning Elena. Weight is 74.2 kg today. A tiny bit of ankle puffiness. Took my Lasix water pill and heart medication.",
                "nurse_reply": "Good morning Linda. 74.2 kg is recorded as your baseline weight. Taking your diuretic on time will help with the ankle puffiness.",
            },
            {
                "day": 2,
                "symptoms": [],
                "meds_taken": True,
                "pain": 0,
                "action": "CONTINUE",
                "patient_msg": "Weight is 74.3 kg. Blood pressure 122/78. Ankle swelling is gone. Low sodium diet followed strictly.",
                "nurse_reply": "Outstanding adherence Linda! Blood pressure of 122/78 and stable weight are ideal indicators for your heart failure recovery.",
            },
            {
                "day": 3,
                "symptoms": [],
                "meds_taken": True,
                "pain": 0,
                "action": "CONTINUE",
                "patient_msg": "Weight is 74.2 kg again. No shortness of breath when lying flat. Took all morning pills.",
                "nurse_reply": "No orthopnea (breathing issues when flat) and stable weight show your fluid balance is well controlled! Keep it up.",
            },
        ],
    },
    {
        "patient_id": "P007",
        "hospital_id": "HOSP-003",
        "name": "David Wilson",
        "age": 52,
        "gender": "Male",
        "diagnosis": "Lumbar L4-L5 Spinal Fusion",
        "risk_score": 0.50,
        "risk_level": "MEDIUM",
        "care_duration_days": 20,
        "monitoring_frequency": "DAILY",
        "completed_days": 2,
        "current_day": 2,
        "prescribed_medications": [
            {"name": "Gabapentin (Neurontin)", "dose": "300mg", "frequency": "Three times daily", "purpose": "Neuropathic nerve pain stabilization post-fusion"},
            {"name": "Methocarbamol (Robaxin)", "dose": "750mg", "frequency": "Twice daily as needed", "purpose": "Muscle relaxant for lumbar paraspinal muscle spasms"},
            {"name": "Acetaminophen", "dose": "650mg", "frequency": "Every 6 hours as needed", "purpose": "Baseline non-opioid pain relief"},
        ],
        "daily_history": [
            {
                "day": 1,
                "symptoms": ["lower back stiffness (4/10)"],
                "meds_taken": True,
                "pain": 4,
                "action": "CONTINUE",
                "patient_msg": "Back brace on whenever I stand. Pain is about 4/10 at the surgical site. Took muscle relaxant and pain pills.",
                "nurse_reply": "Good job wearing your brace, David. Avoid any bending, lifting, or twisting motions. I have logged your Day 1 update.",
            },
            {
                "day": 2,
                "symptoms": ["lower back ache (3/10)"],
                "meds_taken": False,
                "pain": 3,
                "action": "MODIFY_CARE_PLAN",
                "patient_msg": "Pain is 3/10, but I forgot to take my morning nerve medication dose today. Should I double up tonight?",
                "nurse_reply": "Thank you for letting me know, David! Please do NOT double up tonight—just resume your normal prescribed dose on schedule.",
            },
        ],
    },
    {
        "patient_id": "P008",
        "hospital_id": "HOSP-002",
        "name": "Patricia Miller",
        "age": 41,
        "gender": "Female",
        "diagnosis": "Laparoscopic Cholecystectomy (Gallbladder)",
        "risk_score": 0.22,
        "risk_level": "LOW",
        "care_duration_days": 14,
        "monitoring_frequency": "DAILY",
        "completed_days": 1,
        "current_day": 1,
        "prescribed_medications": [
            {"name": "Acetaminophen", "dose": "500mg", "frequency": "Every 6 hours as needed", "purpose": "Incisional pain relief"},
            {"name": "Simethicone", "dose": "125mg", "frequency": "After meals as needed", "purpose": "Relief of laparoscopic gas pressure and shoulder pain"},
        ],
        "daily_history": [
            {
                "day": 1,
                "symptoms": ["right shoulder gas pain (3/10)"],
                "meds_taken": True,
                "pain": 3,
                "action": "CONTINUE",
                "patient_msg": "Hi Elena! Some shoulder ache from the laparoscopic gas, but incisions feel fine. Took pain med as prescribed.",
                "nurse_reply": "Hello Patricia! Diaphragmatic shoulder ache is very common after gallbladder laparoscopy. Gentle walking and a warm heating pad on the shoulder will help!",
            },
        ],
    },
    {
        "patient_id": "P009",
        "hospital_id": "HOSP-001",
        "name": "James Taylor",
        "age": 69,
        "gender": "Male",
        "diagnosis": "Total Hip Arthroplasty (Left Posterior)",
        "risk_score": 0.48,
        "risk_level": "MEDIUM",
        "care_duration_days": 20,
        "monitoring_frequency": "DAILY",
        "completed_days": 3,
        "current_day": 3,
        "prescribed_medications": [
            {"name": "Xarelto (Rivaroxaban)", "dose": "10mg", "frequency": "Once daily with evening meal", "purpose": "Direct oral anticoagulant for DVT prevention post-hip replacement"},
            {"name": "Meloxicam", "dose": "15mg", "frequency": "Once daily morning with breakfast", "purpose": "Once-daily NSAID for surgical hip joint inflammation"},
        ],
        "daily_history": [
            {
                "day": 1,
                "symptoms": ["hip stiffness", "surgical soreness (5/10)"],
                "meds_taken": True,
                "pain": 5,
                "action": "CONTINUE",
                "patient_msg": "Walker used for bathroom trips. Hip sore (5/10). Taking Eliquis blood thinner and pain meds.",
                "nurse_reply": "Good morning James. Remember hip precautions (do not cross legs or bend past 90 degrees). Eliquis adherence is essential to prevent clots.",
            },
            {
                "day": 2,
                "symptoms": ["mild hip stiffness (3/10)"],
                "meds_taken": True,
                "pain": 3,
                "action": "CONTINUE",
                "patient_msg": "Physical therapist visited today. Did gentle glute squeezes. Pain down to 3/10. All meds taken.",
                "nurse_reply": "Excellent progress with physical therapy, James! Keeping your hip moving within safe limits is key to recovery.",
            },
            {
                "day": 3,
                "symptoms": ["mild soreness (2/10)"],
                "meds_taken": True,
                "pain": 2,
                "action": "CONTINUE",
                "patient_msg": "Walked 50 feet with walker comfortably. Dressing is clean and dry. Took all morning pills.",
                "nurse_reply": "Great milestone reaching 50 feet, James! Your Day 3 vitals and medication adherence are 100% recorded.",
            },
        ],
    },
    {
        "patient_id": "P010",
        "hospital_id": "HOSP-003",
        "name": "Barbara Martinez",
        "age": 60,
        "gender": "Female",
        "diagnosis": "Community-Acquired Bacterial Pneumonia",
        "risk_score": 0.68,
        "risk_level": "HIGH",
        "care_duration_days": 20,
        "monitoring_frequency": "DAILY",
        "completed_days": 2,
        "current_day": 2,
        "prescribed_medications": [
            {"name": "Augmentin (Amoxicillin/Clavulanate)", "dose": "875/125mg", "frequency": "Twice daily with meals (Complete full 10-day course)", "purpose": "Broad-spectrum oral antibiotic to eradicate bacterial lung infection"},
            {"name": "Guaifenesin (Mucinex)", "dose": "600mg", "frequency": "Every 12 hours with large glass of water", "purpose": "Expectorant to thin and clear bronchial pulmonary secretions"},
        ],
        "daily_history": [
            {
                "day": 1,
                "symptoms": ["fatigue", "productive cough"],
                "meds_taken": True,
                "pain": 0,
                "action": "CONTINUE",
                "patient_msg": "Still feeling tired. Coughing up clear phlegm. Finished today's oral antibiotic dose on time.",
                "nurse_reply": "Hello Barbara. Completing the full antibiotic course is vital even as you start feeling better. Drink plenty of warm fluids.",
            },
            {
                "day": 2,
                "symptoms": ["mild fatigue"],
                "meds_taken": True,
                "pain": 0,
                "action": "CONTINUE",
                "patient_msg": "Temperature is normal at 98.4°F. Cough is much less frequent. Antibiotics taken with lunch.",
                "nurse_reply": "A normal temperature of 98.4°F is a fantastic indicator that the antibiotic therapy is resolving the infection, Barbara! Rest up today.",
            },
        ],
    },
]


def seed_database(session: Session) -> Dict[str, int]:
    """
    Populates PostgreSQL with 10 detailed patients, discharge medication orders,
    day-by-day longitudinal history, conversations, feedback, actions, schedules, and checkpoints.
    """
    patient_repo = PatientRepository(session)
    hospital_repo = HospitalRepository(session)
    pred_repo = PredictionRepository(session)
    event_repo = EventRepository(session)
    profile_repo = PatientProfileRepository(session)
    care_plan_repo = CarePlanRepository(session)
    feedback_repo = FeedbackRepository(session)
    action_repo = AgentActionRepository(session)
    schedule_repo = ScheduleRepository(session)
    conv_repo = ConversationRepository(session)

    # 1. Seed Hospitals
    hospitals_seeded = 0
    for h in SYNTHETIC_HOSPITALS:
        if not hospital_repo.get_by_code(h["hospital_code"]):
            hospital_repo.create_hospital(
                hospital_id=h["hospital_id"],
                hospital_code=h["hospital_code"],
                hospital_name=h["hospital_name"],
                location=h["location"],
                is_active=h["is_active"],
            )
            hospitals_seeded += 1

    # 2. Seed Patients with Day-by-Day Longitudinal Data
    patients_seeded = 0
    predictions_seeded = 0
    events_seeded = 0
    care_plans_seeded = 0
    feedback_seeded = 0
    actions_seeded = 0
    schedules_seeded = 0
    conversations_seeded = 0

    now = datetime.utcnow()

    for p in PATIENT_SEEDS:
        p_id = p["patient_id"]
        completed_days = p["completed_days"]
        discharge_time = now - timedelta(days=completed_days + 1)

        # 2a. Ensure Patient Record exists
        if not patient_repo.exists(p_id):
            patient_repo.create_patient(p_id)
            patients_seeded += 1

        # 2b. Store ML Prediction
        existing_pred = pred_repo.get_latest_prediction(p_id)
        if not existing_pred:
            pred = pred_repo.create_prediction(
                patient_id=p_id,
                risk_score=p["risk_score"],
                risk_level=p["risk_level"],
                recommended_care_days=p["care_duration_days"],
                model_version="readmission-v1.2",
            )
            predictions_seeded += 1
        else:
            pred = existing_pred

        # 2c. Store Admission & Discharge Events (Day 0)
        event_repo.create_event(
            patient_id=p_id,
            hospital_id=p["hospital_id"],
            event_type="PATIENT_ADMITTED",
            event_timestamp=discharge_time - timedelta(days=3),
            payload={"diagnosis": p["diagnosis"], "age": p["age"], "gender": p["gender"]},
        )
        events_seeded += 1

        event_repo.create_event(
            patient_id=p_id,
            hospital_id=p["hospital_id"],
            event_type="PATIENT_DISCHARGED",
            event_timestamp=discharge_time,
            payload={
                "diagnosis": p["diagnosis"],
                "risk_score": p["risk_score"],
                "risk_level": p["risk_level"],
                "discharge_summary": f"Discharged following {p['diagnosis']}. Enrolled in AI Post-Care.",
                "prescribed_medications": p.get("prescribed_medications", []),
            },
        )
        events_seeded += 1

        # 2d. Create or Update Active Care Plan with Prescribed Medications
        existing_plan = care_plan_repo.get_active_care_plan(p_id)
        plan_dict = {
            "risk_score": p["risk_score"],
            "risk_level": p["risk_level"],
            "diagnosis": p["diagnosis"],
            "patient_name": p["name"],
            "prescribed_medications": p.get("prescribed_medications", []),
        }

        if not existing_plan:
            care_plan = care_plan_repo.create_care_plan(
                patient_id=p_id,
                prediction_id=pred.prediction_id,
                duration_days=p["care_duration_days"],
                current_day=completed_days,
                status="ACTIVE",
                monitoring_frequency=p["monitoring_frequency"],
                plan_data=plan_dict,
            )
            care_plans_seeded += 1
        else:
            existing_plan.plan_data = plan_dict
            session.commit()
            care_plan = existing_plan

        # 2e. Update Patient Profile
        profile_repo.create_or_update_profile(
            patient_id=p_id,
            current_hospital_id=p["hospital_id"],
            care_status="POST_CARE_ACTIVE",
            admitted_at=discharge_time - timedelta(days=3),
            discharged_at=discharge_time,
        )

        # 2f. Seed Day-by-Day Historical Records
        accumulated_symptoms: List[str] = []
        adherence_count = 0
        past_action_records: List[Dict[str, Any]] = []
        adaptation_notes: List[str] = [f"Post-Care activated for {p['diagnosis']} (Baseline: {p['risk_level']})"]

        for day_record in p["daily_history"]:
            d_num = day_record["day"]
            d_time = discharge_time + timedelta(days=d_num, hours=9)

            # Update adherence tracking
            if day_record["meds_taken"]:
                adherence_count += 1
            accumulated_symptoms = list(day_record["symptoms"])

            # 1. Hospital Daily Event
            event_repo.create_event(
                patient_id=p_id,
                hospital_id=p["hospital_id"],
                event_type="DAILY_CHECKIN",
                event_timestamp=d_time,
                payload={
                    "day": d_num,
                    "symptoms": day_record["symptoms"],
                    "medication_taken": day_record["meds_taken"],
                    "pain_score": day_record["pain"],
                    "text": day_record["patient_msg"],
                },
            )
            events_seeded += 1

            # 2. Structured Feedback
            feedback_repo.create_feedback(
                patient_id=p_id,
                day=d_num,
                feedback_type="DAILY_CHECKIN",
                care_plan_id=care_plan.care_plan_id,
                raw_feedback=day_record["patient_msg"],
                structured_feedback={
                    "extracted_symptoms": day_record["symptoms"],
                    "medication_taken": day_record["meds_taken"],
                    "pain_score": day_record["pain"],
                    "data_quality": "GOOD",
                },
            )
            feedback_seeded += 1

            # 3. Agent Action Audit Record
            action_rec = action_repo.record_action(
                patient_id=p_id,
                day=d_num,
                node_name="act_node",
                action_type=day_record["action"],
                care_plan_id=care_plan.care_plan_id,
                reason=f"Day {d_num} recovery routine evaluation",
                tool_name="log_intervention" if day_record["action"] == "CONTINUE" else "schedule_followup",
                result={"status": "EXECUTED", "day": d_num},
            )
            past_action_records.append({
                "action": day_record["action"],
                "day": d_num,
                "status": "EXECUTED",
            })
            actions_seeded += 1

            # 4. Completed Schedule
            schedule_repo.create_schedule(
                patient_id=p_id,
                care_day=d_num,
                scheduled_at=d_time,
                frequency=p["monitoring_frequency"],
                care_plan_id=care_plan.care_plan_id,
                status="COMPLETED",
            )
            schedules_seeded += 1

            # 5. Conversation Dialogue Turns in patient_conversations
            # Nurse Opening
            conv_repo.save_message(
                chat_id=p_id,
                role="assistant",
                message_text=f"Good morning {p['name']}! Nurse Elena checking in for Day {d_num} of your recovery. How are you feeling today?",
                patient_id=p_id,
                channel="TELEGRAM",
            )
            # Patient Message
            conv_repo.save_message(
                chat_id=p_id,
                role="patient",
                message_text=day_record["patient_msg"],
                patient_id=p_id,
                channel="TELEGRAM",
            )
            # Nurse Advice
            conv_repo.save_message(
                chat_id=p_id,
                role="assistant",
                message_text=day_record["nurse_reply"],
                patient_id=p_id,
                channel="TELEGRAM",
            )
            conversations_seeded += 3

            adaptation_notes.append(f"Day {d_num}: Action={day_record['action']}, Symptoms={day_record['symptoms']}")

        # 2g. Create Next Active Schedule (Day completed_days + 1)
        next_day = completed_days + 1
        schedule_repo.create_schedule(
            patient_id=p_id,
            care_day=next_day,
            scheduled_at=now + timedelta(hours=2),
            frequency=p["monitoring_frequency"],
            care_plan_id=care_plan.care_plan_id,
            status="SCHEDULED",
        )
        schedules_seeded += 1

        # 2h. Store Checkpointed State Machine in langgraph_checkpoints via PostgresSaver
        current_adherence = round(adherence_count / max(completed_days, 1), 2)
        state_checkpoint_values = {
            "patient_id": p_id,
            "current_day": completed_days,
            "care_duration_days": p["care_duration_days"],
            "risk_level": p["risk_level"],
            "current_risk_score": p["risk_score"],
            "symptoms": accumulated_symptoms,
            "medication_adherence": current_adherence,
            "monitoring_frequency": p["monitoring_frequency"],
            "plan_status": "ACTIVE",
            "current_action": "CONTINUE",
            "next_action": None,
            "escalation_required": False,
            "data_quality": "GOOD",
            "adaptation_notes": adaptation_notes,
            "previous_actions": past_action_records,
        }

        # Checkpointer write
        checkpointer = PostgresSaver(db_manager=get_db_session_manager())
        try:
            checkpointer.put(
                {"configurable": {"thread_id": p_id, "checkpoint_ns": ""}},
                {"channel_values": state_checkpoint_values, "values": state_checkpoint_values, "id": f"seed_cp_{p_id}"},
                {"source": "seed_data", "step": completed_days},
                {},
            )
        except Exception:
            pass

    return {
        "hospitals": hospitals_seeded,
        "patients": patients_seeded,
        "predictions": predictions_seeded,
        "events": events_seeded,
        "care_plans": care_plans_seeded,
        "feedback_entries": feedback_seeded,
        "actions_logged": actions_seeded,
        "schedules_created": schedules_seeded,
        "conversation_messages": conversations_seeded,
    }


if __name__ == "__main__":
    db_manager = get_db_session_manager()
    with db_manager.session_scope() as session:
        stats = seed_database(session)
        print("\n" + "=" * 60)
        print(" [+] POSTGRESQL LONGITUDINAL DATABASE SEED COMPLETED")
        print("=" * 60)
        for k, v in stats.items():
            print(f"  * {k:<25}: {v}")
        print("=" * 60 + "\n")
