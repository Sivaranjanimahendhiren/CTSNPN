"""
Hospital Event Adapter:
Integration layer connecting external hospital lifecycle events (EHR / Webhooks)
to PostgreSQL persistence and the EXISTING MultiPatientOrchestrator.
Does NOT contain adaptive care business logic or LangGraph node definitions.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from ..schemas.patient_event import PatientEvent, EventTypeEnum
from ..storage.database import DatabaseSessionManager, get_db_session_manager
from ..storage.repositories import (
    PatientRepository,
    HospitalRepository,
    PredictionRepository,
    EventRepository,
    PatientProfileRepository,
    CarePlanRepository,
    ScheduleRepository,
)
from ..orchestrator import MultiPatientOrchestrator


from ..scheduling import MonitoringScheduler


class HospitalEventAdapter:
    """
    Adapter translating external hospital lifecycle events into PostgreSQL updates
    and invoking the existing MultiPatientOrchestrator only when appropriate.
    """

    def __init__(
        self,
        orchestrator: Optional[MultiPatientOrchestrator] = None,
        db_manager: Optional[DatabaseSessionManager] = None,
        repository: Optional[Any] = None,
        scheduler: Optional[MonitoringScheduler] = None,
    ):
        self.orchestrator = orchestrator or MultiPatientOrchestrator()
        if repository is not None and hasattr(repository, "db"):
            self.db = repository.db
            self.repository = repository
        else:
            self.db = db_manager or get_db_session_manager()
            self.repository = repository
        self.scheduler = scheduler or MonitoringScheduler(db_manager=self.db)

    def ingest_prediction(
        self,
        patient_id: str,
        risk_score: float,
        risk_level: str,
        recommended_care_days: int,
        model_version: str = "1.0.0",
    ) -> Dict[str, Any]:
        """Convenience method to ingest a prediction."""
        from ..services.readmission_prediction_service import ReadmissionPredictionService
        svc = ReadmissionPredictionService(db_manager=self.db)
        return svc.ingest_prediction({
            "patient_id": patient_id,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "recommended_care_days": recommended_care_days,
            "model_version": model_version,
        })

    def process_hospital_event(
        self,
        event_data: Union[Dict[str, Any], PatientEvent],
    ) -> Dict[str, Any]:
        """
        Main entry point for hospital event stream.
        Routes events according to their lifecycle type.
        """
        # 1. Normalize and validate incoming event
        if isinstance(event_data, PatientEvent):
            p_id = event_data.patient_id
            h_id = event_data.hospital_id
            e_type = str(event_data.event_type.value if hasattr(event_data.event_type, "value") else event_data.event_type).upper()
            e_ts = event_data.event_timestamp
            payload = event_data.payload or (event_data.feedback.model_dump() if hasattr(event_data.feedback, "model_dump") else event_data.feedback) or {}
            event_dict = event_data.model_dump()
        elif isinstance(event_data, dict):
            p_id = str(event_data.get("patient_id", "")).strip()
            h_id = event_data.get("hospital_id")
            e_type = str(event_data.get("event_type", "")).strip().upper()
            e_ts = event_data.get("event_timestamp")
            payload = event_data.get("payload") or event_data.get("feedback") or {}
            event_dict = dict(event_data)
        else:
            raise ValueError(f"Unsupported event data type: {type(event_data)}")

        if not p_id:
            raise ValueError("patient_id is required for all hospital events")
        if not e_type:
            raise ValueError("event_type is required for all hospital events")

        # Parse timestamp if string
        event_datetime = datetime.utcnow()
        if e_ts:
            if isinstance(e_ts, datetime):
                event_datetime = e_ts
            elif isinstance(e_ts, str):
                try:
                    event_datetime = datetime.fromisoformat(e_ts.replace("Z", "+00:00"))
                except Exception:
                    event_datetime = datetime.utcnow()

        with self.db.session_scope() as session:
            p_repo = PatientRepository(session)
            h_repo = HospitalRepository(session)
            pred_repo = PredictionRepository(session)
            evt_repo = EventRepository(session)
            prof_repo = PatientProfileRepository(session)
            plan_repo = CarePlanRepository(session)

            # Ensure minimal patient record exists
            if not p_repo.exists(p_id):
                p_repo.create_patient(p_id)

            # Ensure hospital exists if provided and resolve UUID hospital_id
            resolved_h_id = None
            if h_id:
                hosp = h_repo.get_hospital(h_id)
                if not hosp:
                    hosp = h_repo.get_by_code(h_id)
                if not hosp:
                    try:
                        hosp = h_repo.create_hospital(hospital_code=h_id, hospital_name=f"Hospital {h_id}")
                    except Exception:
                        hosp = h_repo.get_by_code(h_id)
                if hosp:
                    resolved_h_id = hosp.hospital_id

            # 2. Store event in hospital_events table
            evt_repo.create_event(
                patient_id=p_id,
                hospital_id=resolved_h_id,
                event_type=e_type,
                event_timestamp=event_datetime,
                payload=payload,
            )

            # =============================================================
            # EVENT: PATIENT_ADMITTED
            # =============================================================
            if e_type == EventTypeEnum.PATIENT_ADMITTED.value.upper() or e_type == "PATIENT_ADMITTED":
                prof_repo.create_or_update_profile(
                    patient_id=p_id,
                    care_status="ADMITTED",
                    current_hospital_id=resolved_h_id,
                    admission_id=payload.get("admission_id"),
                    admitted_at=event_datetime,
                )
                return {
                    "patient_id": p_id,
                    "event_type": "PATIENT_ADMITTED",
                    "status": "ADMITTED",
                    "agent_active": False,
                    "message": f"Patient {p_id} admitted in hospital. Agent is dormant.",
                }

            # =============================================================
            # EVENT: PATIENT_DISCHARGED (Primary Trigger for Agent)
            # =============================================================
            elif e_type == EventTypeEnum.PATIENT_DISCHARGED.value.upper() or e_type == "PATIENT_DISCHARGED":
                # Idempotency check: verify if already active in post-care
                existing_profile = prof_repo.get_profile(p_id)
                active_plan = plan_repo.get_active_care_plan(p_id)

                if existing_profile and existing_profile.care_status == "POST_CARE_ACTIVE" and active_plan:
                    if self.orchestrator and (p_id not in self.orchestrator.list_patients() and self.orchestrator.get_patient_state(p_id) is None):
                        self.orchestrator.register_patient(
                            patient_id=p_id,
                            risk_score=active_plan.plan_data.get("risk_score", 0.0) if active_plan.plan_data else 0.0,
                            risk_level=active_plan.plan_data.get("risk_level", "LOW") if active_plan.plan_data else "LOW",
                            care_duration_days=active_plan.duration_days,
                            clinical_notes="Hydrated from active care plan",
                        )

                    # Ensure a pending schedule exists if none is scheduled yet
                    if self.scheduler:
                        sched_repo = ScheduleRepository(session)
                        if not sched_repo.get_pending_schedules(p_id):
                            self.scheduler.schedule_first_checkin(
                                patient_id=p_id,
                                care_plan_id=active_plan.care_plan_id,
                                frequency=active_plan.monitoring_frequency or "DAILY",
                                start_date=event_datetime,
                            )

                    return {
                        "patient_id": p_id,
                        "event_type": "PATIENT_DISCHARGED",
                        "status": "POST_CARE_ACTIVATED",
                        "agent_active": True,
                        "risk_level": active_plan.plan_data.get("risk_level", "UNKNOWN") if active_plan.plan_data else "UNKNOWN",
                        "risk_score": active_plan.plan_data.get("risk_score", 0.0) if active_plan.plan_data else 0.0,
                        "care_duration_days": active_plan.duration_days,
                        "message": "Duplicate discharge event ignored; patient is already active in post-care.",
                    }

                # Retrieve latest prediction from PostgreSQL (or payload if provided in event)
                latest_pred = pred_repo.get_latest_prediction(p_id)
                if not latest_pred and payload and ("risk_score" in payload or "risk_level" in payload):
                    latest_pred = pred_repo.create_prediction(
                        patient_id=p_id,
                        risk_score=float(payload.get("risk_score", 0.5)),
                        risk_level=str(payload.get("risk_level", "MEDIUM")),
                        recommended_care_days=int(payload.get("care_duration_days", 30)),
                        model_version=str(payload.get("model_version", "readmission-v1")),
                    )

                # EDGE CASE: No prediction exists
                if not latest_pred:
                    prof_repo.create_or_update_profile(
                        patient_id=p_id,
                        care_status="DISCHARGED",
                        current_hospital_id=resolved_h_id,
                        discharged_at=event_datetime,
                    )
                    return {
                        "patient_id": p_id,
                        "event_type": "PATIENT_DISCHARGED",
                        "status": "WAITING_FOR_RISK_ASSESSMENT",
                        "agent_active": False,
                        "reason": f"No readmission prediction found for patient '{p_id}'. Agent activation deferred.",
                    }

                # VALID PREDICTION FOUND: Activate Post-Care
                risk_score = latest_pred.risk_score
                risk_level = latest_pred.risk_level
                care_days = latest_pred.recommended_care_days  # Dynamic duration from ML model

                # 1. Call EXISTING MultiPatientOrchestrator
                registered_state = self.orchestrator.register_patient(
                    patient_id=p_id,
                    risk_score=risk_score,
                    risk_level=risk_level,
                    care_duration_days=care_days,
                    clinical_notes=payload.get("discharge_summary") or f"Discharged from hospital {h_id or ''}",
                )

                # 2. Persist CarePlan to PostgreSQL
                created_plan = plan_repo.create_care_plan(
                    patient_id=p_id,
                    prediction_id=latest_pred.prediction_id,
                    duration_days=care_days,
                    current_day=0,
                    status="ACTIVE",
                    monitoring_frequency=registered_state.get("monitoring_frequency", "DAILY"),
                    plan_data={
                        "risk_score": risk_score,
                        "risk_level": risk_level,
                        "model_version": latest_pred.model_version,
                    },
                )

                # 3. Update Patient Profile to POST_CARE_ACTIVE
                prof_repo.create_or_update_profile(
                    patient_id=p_id,
                    care_status="POST_CARE_ACTIVE",
                    current_hospital_id=resolved_h_id,
                    discharged_at=event_datetime,
                )

                # 4. Schedule First Check-in (Day 1)
                first_sched = self.scheduler.schedule_first_checkin(
                    patient_id=p_id,
                    care_plan_id=created_plan.care_plan_id,
                    frequency=registered_state.get("monitoring_frequency", "DAILY"),
                    start_date=event_datetime,
                )

                return {
                    "patient_id": p_id,
                    "event_type": "PATIENT_DISCHARGED",
                    "status": "POST_CARE_ACTIVATED",
                    "agent_active": True,
                    "risk_level": risk_level,
                    "risk_score": risk_score,
                    "care_duration_days": care_days,
                    "first_checkin_scheduled": first_sched,
                    "patient_state": registered_state,
                }

            # =============================================================
            # EVENT: PATIENT_READMITTED
            # =============================================================
            elif e_type == EventTypeEnum.PATIENT_READMITTED.value.upper() or e_type == "PATIENT_READMITTED":
                prof_repo.create_or_update_profile(
                    patient_id=p_id,
                    care_status="READMITTED",
                    current_hospital_id=resolved_h_id,
                    admission_id=payload.get("admission_id"),
                    admitted_at=event_datetime,
                )

                # Pause active care plan in PostgreSQL
                active_plan = plan_repo.get_active_care_plan(p_id)
                if active_plan:
                    plan_repo.update_care_plan(active_plan.care_plan_id, status="PAUSED")

                # Cancel / pause pending scheduled monitoring
                self.scheduler.cancel_pending_schedules(p_id, reason="READMITTED")

                # Pause active monitoring in orchestrator
                if p_id in self.orchestrator.list_patients():
                    self.orchestrator.pause_patient(p_id, reason="Hospital Readmission")

                return {
                    "patient_id": p_id,
                    "event_type": "PATIENT_READMITTED",
                    "status": "POST_CARE_PAUSED",
                    "agent_active": False,
                    "message": f"Patient {p_id} readmitted. Care plan paused. All history preserved.",
                }

            # =============================================================
            # ROUTINE / CLINICAL EVENTS (DAILY_CHECKIN, CONSULTATION, APPT, MISSED, etc.)
            # =============================================================
            else:
                # Ensure patient is loaded in orchestrator if active care plan exists in database
                if self.orchestrator:
                    if p_id not in self.orchestrator.list_patients() and self.orchestrator.get_patient_state(p_id) is None:
                        active_plan = plan_repo.get_active_care_plan(p_id)
                        if active_plan:
                            self.orchestrator.register_patient(
                                patient_id=p_id,
                                risk_score=active_plan.plan_data.get("risk_score", 0.0) if active_plan.plan_data else 0.0,
                                risk_level=active_plan.plan_data.get("risk_level", "LOW") if active_plan.plan_data else "LOW",
                                care_duration_days=active_plan.duration_days,
                                clinical_notes="Hydrated from active care plan",
                            )

                # If patient is actively enrolled in orchestrator, route event through graph
                if self.orchestrator and (p_id in self.orchestrator.list_patients() or self.orchestrator.get_patient_state(p_id) is not None):
                    # Format event dictionary for orchestrator
                    if "day" not in event_dict or event_dict.get("day", 0) == 0:
                        current_st = self.orchestrator.get_patient_state(p_id)
                        curr_day = current_st.get("current_day", 1) if current_st else 1
                        event_dict["day"] = curr_day

                    event_dict["event_type"] = e_type.lower()
                    event_dict["feedback"] = payload

                    updated_state = self.orchestrator.process_patient_event(event_dict)
                    care_day = updated_state.get("current_day", 1)
                    duration_days = updated_state.get("care_duration_days", 30)
                    freq = updated_state.get("monitoring_frequency", "DAILY")
                    plan_stat = updated_state.get("plan_status", "ACTIVE")

                    # Complete current check-in in scheduler
                    self.scheduler.complete_current_checkin(p_id, care_day=care_day)

                    # Determine next check-in or completion
                    next_sched = None
                    if plan_stat == "ACTIVE" and care_day < duration_days:
                        next_sched = self.scheduler.schedule_next_checkin(
                            patient_id=p_id,
                            current_day=care_day,
                            frequency=freq,
                            care_duration_days=duration_days,
                        )
                    elif care_day >= duration_days:
                        # Update DB care plan to COMPLETED
                        active_plan = plan_repo.get_active_care_plan(p_id)
                        if active_plan:
                            plan_repo.update_care_plan(active_plan.care_plan_id, status="COMPLETED")
                        prof_repo.create_or_update_profile(patient_id=p_id, care_status="CARE_COMPLETED")

                    return {
                        "patient_id": p_id,
                        "event_type": e_type,
                        "status": plan_stat,
                        "agent_active": True,
                        "current_day": care_day,
                        "monitoring_frequency": freq,
                        "next_checkin_scheduled": next_sched,
                        "patient_state": updated_state,
                    }
                else:
                    return {
                        "patient_id": p_id,
                        "event_type": e_type,
                        "status": "STORED",
                        "agent_active": False,
                        "message": f"Event {e_type} recorded in database.",
                    }

    # Backward compatibility alias
    handle_event = process_hospital_event
