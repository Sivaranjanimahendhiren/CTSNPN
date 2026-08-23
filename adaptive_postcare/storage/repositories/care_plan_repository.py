"""
Repository for CarePlan entity operations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from ..models import CarePlan, generate_uuid


class CarePlanRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_care_plan(
        self,
        patient_id: str,
        duration_days: int,
        prediction_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        current_day: int = 0,
        status: str = "INITIALIZED",
        monitoring_frequency: str = "DAILY",
        plan_data: Optional[Dict[str, Any]] = None,
        care_plan_id: Optional[str] = None,
    ) -> CarePlan:
        """
        Creates a new care plan.
        Duration MUST be flexible (e.g. 10, 14, 15, 20, 30 days) and sourced from prediction.
        """
        if duration_days < 1:
            raise ValueError(f"duration_days must be >= 1, got {duration_days}")

        plan = CarePlan(
            care_plan_id=care_plan_id or generate_uuid(),
            patient_id=str(patient_id).strip(),
            prediction_id=prediction_id,
            start_date=start_date or datetime.utcnow(),
            duration_days=int(duration_days),
            current_day=int(current_day),
            status=str(status).strip().upper(),
            monitoring_frequency=str(monitoring_frequency).strip().upper(),
            plan_data=plan_data or {},
        )
        self.session.add(plan)
        self.session.commit()
        self.session.refresh(plan)
        return plan

    def get_active_care_plan(self, patient_id: str) -> Optional[CarePlan]:
        """Retrieves the currently active or initialized care plan for a patient."""
        return (
            self.session.query(CarePlan)
            .filter(
                CarePlan.patient_id == patient_id,
                CarePlan.status.in_(["ACTIVE", "INITIALIZED", "ESCALATED", "PAUSED"]),
            )
            .order_by(CarePlan.created_at.desc())
            .first()
        )

    def get_care_plan(self, care_plan_id: str) -> Optional[CarePlan]:
        """Retrieves care plan by care_plan_id."""
        return self.session.query(CarePlan).filter(CarePlan.care_plan_id == care_plan_id).first()

    def update_care_plan(
        self,
        care_plan_id: str,
        current_day: Optional[int] = None,
        status: Optional[str] = None,
        monitoring_frequency: Optional[str] = None,
        plan_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[CarePlan]:
        """Updates progression or status of an existing care plan."""
        plan = self.get_care_plan(care_plan_id)
        if not plan:
            return None

        if current_day is not None:
            plan.current_day = int(current_day)
        if status is not None:
            plan.status = str(status).strip().upper()
        if monitoring_frequency is not None:
            plan.monitoring_frequency = str(monitoring_frequency).strip().upper()
        if plan_data is not None:
            plan.plan_data = plan_data

        plan.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(plan)
        return plan

    def list_patient_care_plans(self, patient_id: str) -> List[CarePlan]:
        """Lists all historical and current care plans for a patient."""
        return (
            self.session.query(CarePlan)
            .filter(CarePlan.patient_id == patient_id)
            .order_by(CarePlan.created_at.asc())
            .all()
        )
