"""
Readmission Prediction Ingestion Service:
Responsible ONLY for receiving, validating, and persisting external ML model readmission outputs.
Does NOT invoke LangGraph, does NOT create care plans, and does NOT alter patient post-care status.
"""

from typing import Any, Dict, List, Optional, Union
from ..schemas.readmission_input import InitialRiskEvent
from ..storage.database import DatabaseSessionManager, get_db_session_manager
from ..storage.repositories import (
    PatientRepository,
    PredictionRepository,
    AgentActionRepository,
)


class ReadmissionPredictionService:
    """
    Independent service handling external readmission model outputs.
    """

    def __init__(self, db_manager: Optional[DatabaseSessionManager] = None):
        self.db = db_manager or get_db_session_manager()

    def ingest_prediction(
        self,
        payload: Union[InitialRiskEvent, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Validates and stores an external ML readmission prediction in PostgreSQL.
        Maintains complete prediction history across multiple submissions.
        """
        # 1. Validate payload using InitialRiskEvent schema
        if isinstance(payload, InitialRiskEvent):
            event = payload
        elif isinstance(payload, dict):
            event = InitialRiskEvent(**payload)
        else:
            raise ValueError(f"Invalid payload type: {type(payload)}")

        # 2. Persist to PostgreSQL
        with self.db.session_scope() as session:
            patient_repo = PatientRepository(session)
            pred_repo = PredictionRepository(session)
            action_repo = AgentActionRepository(session)

            # Ensure minimal patient record exists
            if not patient_repo.exists(event.patient_id):
                patient_repo.create_patient(event.patient_id)

            # Store Prediction record
            pred = pred_repo.create_prediction(
                patient_id=event.patient_id,
                risk_score=event.risk_score,
                risk_level=event.risk_level.value if hasattr(event.risk_level, "value") else str(event.risk_level),
                recommended_care_days=event.recommended_care_days or event.care_duration_days,
                model_version=event.model_version or "readmission-v1",
            )

            # Record audit event without pretending LangGraph ran
            action_repo.record_action(
                patient_id=event.patient_id,
                day=0,
                node_name="ExternalReadmissionModel",
                action_type="READMISSION_PREDICTION_STORED",
                reason=f"Model {pred.model_version} output stored with score {pred.risk_score}",
                result={
                    "prediction_id": pred.prediction_id,
                    "risk_level": pred.risk_level,
                    "recommended_care_days": pred.recommended_care_days,
                },
            )

            return {
                "prediction_id": pred.prediction_id,
                "patient_id": pred.patient_id,
                "risk_score": pred.risk_score,
                "risk_level": pred.risk_level,
                "recommended_care_days": pred.recommended_care_days,
                "model_version": pred.model_version,
                "status": "stored",
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

    def get_prediction_history(self, patient_id: str) -> List[Dict[str, Any]]:
        """Retrieves all historical predictions logged for a patient in chronological order."""
        with self.db.session_scope() as session:
            pred_repo = PredictionRepository(session)
            history = pred_repo.get_prediction_history(patient_id)
            return [
                {
                    "prediction_id": p.prediction_id,
                    "patient_id": p.patient_id,
                    "risk_score": p.risk_score,
                    "risk_level": p.risk_level,
                    "recommended_care_days": p.recommended_care_days,
                    "model_version": p.model_version,
                    "created_at": str(p.created_at),
                }
                for p in history
            ]
