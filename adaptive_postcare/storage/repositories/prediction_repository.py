"""
Repository for ReadmissionPrediction entity operations.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from ..models import ReadmissionPrediction, generate_uuid


class PredictionRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_prediction(
        self,
        patient_id: str,
        risk_score: float,
        risk_level: str,
        recommended_care_days: int,
        model_version: str = "1.0.0",
        prediction_id: Optional[str] = None,
    ) -> ReadmissionPrediction:
        """Stores output from an external ML readmission model."""
        if not (0.0 <= risk_score <= 1.0):
            raise ValueError(f"risk_score must be between 0.0 and 1.0, got {risk_score}")
        if recommended_care_days < 1:
            raise ValueError(f"recommended_care_days must be >= 1, got {recommended_care_days}")

        pred = ReadmissionPrediction(
            prediction_id=prediction_id or generate_uuid(),
            patient_id=str(patient_id).strip(),
            risk_score=float(risk_score),
            risk_level=str(risk_level).strip().upper(),
            recommended_care_days=int(recommended_care_days),
            model_version=str(model_version).strip(),
        )
        self.session.add(pred)
        self.session.commit()
        self.session.refresh(pred)
        return pred

    def get_prediction_history(self, patient_id: str) -> List[ReadmissionPrediction]:
        """Retrieves all predictions logged for a patient in chronological order."""
        return (
            self.session.query(ReadmissionPrediction)
            .filter(ReadmissionPrediction.patient_id == patient_id)
            .order_by(ReadmissionPrediction.created_at.asc())
            .all()
        )

    def get_latest_prediction(self, patient_id: str) -> Optional[ReadmissionPrediction]:
        """Retrieves the most recent readmission prediction for a patient."""
        history = self.get_prediction_history(patient_id)
        return history[-1] if history else None
