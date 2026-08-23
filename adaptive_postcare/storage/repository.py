"""
Repository facade providing backward-compatible access to predictions, hospital events, and lifecycles.
Delegates to the granular SQLAlchemy repositories.
"""

from typing import Any, Dict, List, Optional
from .database import DatabaseSessionManager, get_db_session_manager
from .repositories import (
    PatientRepository,
    PredictionRepository,
    EventRepository,
    PatientProfileRepository,
)


class StorageRepository:
    """
    Unified Data Access facade delegating to individual domain repositories.
    """

    def __init__(self, db_manager: Optional[DatabaseSessionManager] = None):
        self.db = db_manager or get_db_session_manager()

    def save_prediction(
        self,
        patient_id: str,
        risk_score: float,
        risk_level: str,
        recommended_care_days: int,
        model_version: str = "1.0.0",
    ) -> Dict[str, Any]:
        """Saves a new ML readmission prediction record."""
        with self.db.session_scope() as session:
            # Ensure patient exists
            p_repo = PatientRepository(session)
            if not p_repo.exists(patient_id):
                p_repo.create_patient(patient_id)

            pred_repo = PredictionRepository(session)
            pred = pred_repo.create_prediction(
                patient_id=patient_id,
                risk_score=risk_score,
                risk_level=risk_level,
                recommended_care_days=recommended_care_days,
                model_version=model_version,
            )
            return {
                "prediction_id": pred.prediction_id,
                "patient_id": pred.patient_id,
                "risk_score": pred.risk_score,
                "risk_level": pred.risk_level,
                "recommended_care_days": pred.recommended_care_days,
                "model_version": pred.model_version,
            }

    def get_latest_prediction(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent readmission prediction for a patient."""
        with self.db.session_scope() as session:
            pred_repo = PredictionRepository(session)
            pred = pred_repo.get_latest_prediction(patient_id)
            if not pred:
                return None
            return {
                "prediction_id": pred.prediction_id,
                "patient_id": pred.patient_id,
                "risk_score": pred.risk_score,
                "risk_level": pred.risk_level,
                "recommended_care_days": pred.recommended_care_days,
                "model_version": pred.model_version,
                "created_at": str(pred.created_at),
            }

    def save_hospital_event(
        self,
        patient_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Logs a hospital event to the event stream."""
        with self.db.session_scope() as session:
            p_repo = PatientRepository(session)
            if not p_repo.exists(patient_id):
                p_repo.create_patient(patient_id)

            event_repo = EventRepository(session)
            event = event_repo.create_event(
                patient_id=patient_id,
                event_type=event_type,
                payload=payload,
            )
            return {
                "event_id": event.event_id,
                "patient_id": event.patient_id,
                "event_type": event.event_type,
                "payload": event.payload,
            }

    def get_hospital_events(self, patient_id: str) -> List[Dict[str, Any]]:
        """Retrieves all hospital events for a given patient."""
        with self.db.session_scope() as session:
            event_repo = EventRepository(session)
            events = event_repo.get_patient_events(patient_id)
            return [
                {
                    "event_id": e.event_id,
                    "patient_id": e.patient_id,
                    "event_type": e.event_type,
                    "payload": e.payload,
                    "created_at": str(e.created_at),
                }
                for e in events
            ]

    def update_patient_lifecycle(self, patient_id: str, status: str) -> str:
        """Updates or sets the patient lifecycle status."""
        with self.db.session_scope() as session:
            p_repo = PatientRepository(session)
            if not p_repo.exists(patient_id):
                p_repo.create_patient(patient_id)

            prof_repo = PatientProfileRepository(session)
            prof = prof_repo.create_or_update_profile(patient_id=patient_id, care_status=status)
            return prof.care_status

    def get_patient_lifecycle(self, patient_id: str) -> Optional[str]:
        """Retrieves the current lifecycle status for a patient."""
        with self.db.session_scope() as session:
            prof_repo = PatientProfileRepository(session)
            prof = prof_repo.get_profile(patient_id)
            return prof.care_status if prof else None
