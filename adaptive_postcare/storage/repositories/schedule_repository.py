"""
Schedule Repository: Data access for patient monitoring schedules.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from ..models import MonitoringSchedule


class ScheduleRepository:
    """
    CRUD repository for managing scheduled monitoring check-ins.
    """

    def __init__(self, session: Session):
        self.session = session

    def create_schedule(
        self,
        patient_id: str,
        care_day: int,
        scheduled_at: datetime,
        frequency: str = "DAILY",
        care_plan_id: Optional[str] = None,
        status: str = "SCHEDULED",
    ) -> MonitoringSchedule:
        """Creates a new scheduled monitoring entry."""
        sched = MonitoringSchedule(
            patient_id=patient_id,
            care_plan_id=care_plan_id,
            care_day=care_day,
            scheduled_at=scheduled_at,
            frequency=frequency,
            status=status,
        )
        self.session.add(sched)
        self.session.commit()
        self.session.refresh(sched)
        return sched

    def get_schedule(self, schedule_id: str) -> Optional[MonitoringSchedule]:
        """Retrieves a schedule by ID."""
        return self.session.query(MonitoringSchedule).filter(MonitoringSchedule.schedule_id == schedule_id).first()

    def get_pending_schedules(self, patient_id: str) -> List[MonitoringSchedule]:
        """Retrieves active/pending schedules for a patient."""
        return (
            self.session.query(MonitoringSchedule)
            .filter(
                MonitoringSchedule.patient_id == patient_id,
                MonitoringSchedule.status == "SCHEDULED",
            )
            .order_by(MonitoringSchedule.scheduled_at.asc())
            .all()
        )

    def get_patient_schedules(self, patient_id: str) -> List[MonitoringSchedule]:
        """Retrieves all schedules for a patient in chronological order."""
        return (
            self.session.query(MonitoringSchedule)
            .filter(MonitoringSchedule.patient_id == patient_id)
            .order_by(MonitoringSchedule.scheduled_at.asc())
            .all()
        )

    def update_schedule_status(
        self,
        schedule_id: str,
        status: str,
        completed_at: Optional[datetime] = None,
    ) -> Optional[MonitoringSchedule]:
        """Updates the status of a schedule (e.g. COMPLETED, MISSED, CANCELLED)."""
        sched = self.get_schedule(schedule_id)
        if not sched:
            return None
        sched.status = status
        if completed_at or status == "COMPLETED":
            sched.completed_at = completed_at or datetime.utcnow()
        self.session.commit()
        self.session.refresh(sched)
        return sched

    def cancel_pending_schedules(self, patient_id: str) -> int:
        """Cancels all pending scheduled check-ins for a patient."""
        pending = self.get_pending_schedules(patient_id)
        for s in pending:
            s.status = "CANCELLED"
        self.session.commit()
        return len(pending)
