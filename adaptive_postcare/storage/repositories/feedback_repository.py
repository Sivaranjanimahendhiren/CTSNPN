"""
Repository for PatientFeedback entity operations.
"""

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from ..models import PatientFeedback, generate_uuid


class FeedbackRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_feedback(
        self,
        patient_id: str,
        day: int,
        feedback_type: str = "DAILY_CHECKIN",
        care_plan_id: Optional[str] = None,
        raw_feedback: Optional[str] = None,
        structured_feedback: Optional[Dict[str, Any]] = None,
        feedback_id: Optional[str] = None,
    ) -> PatientFeedback:
        """Stores structured patient check-in or feedback entry."""
        feedback = PatientFeedback(
            feedback_id=feedback_id or generate_uuid(),
            patient_id=str(patient_id).strip(),
            care_plan_id=care_plan_id,
            day=int(day),
            feedback_type=str(feedback_type).strip().upper(),
            raw_feedback=raw_feedback,
            structured_feedback=structured_feedback or {},
        )
        self.session.add(feedback)
        self.session.commit()
        self.session.refresh(feedback)
        return feedback

    def get_feedback_history(
        self,
        patient_id: str,
        care_plan_id: Optional[str] = None,
    ) -> List[PatientFeedback]:
        """Retrieves patient feedback entries in chronological order."""
        query = self.session.query(PatientFeedback).filter(PatientFeedback.patient_id == patient_id)
        if care_plan_id:
            query = query.filter(PatientFeedback.care_plan_id == care_plan_id)
        return query.order_by(PatientFeedback.day.asc(), PatientFeedback.created_at.asc()).all()
