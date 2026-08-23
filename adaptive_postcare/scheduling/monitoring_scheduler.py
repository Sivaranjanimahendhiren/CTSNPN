"""
Monitoring Scheduler:
Determines when the patient should be contacted, maintains scheduled check-ins in PostgreSQL,
and handles dynamic cadence changes, missed check-ins, readmission pauses, and plan completion.
Does NOT perform clinical reasoning (clinical reasoning stays inside LangGraph).
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from ..storage.database import DatabaseSessionManager, get_db_session_manager
from ..storage.repositories import ScheduleRepository, CarePlanRepository, PatientProfileRepository


CADENCE_HOURS_MAP = {
    "HOURLY_6": 6,
    "HOURLY_12": 12,
    "TWICE_DAILY": 12,
    "DAILY": 24,
    "ROUTINE": 24,
}


class MonitoringScheduler:
    """
    Scheduler responsible for timing patient touchpoints based on agent-directed cadence.
    """

    def __init__(self, db_manager: Optional[DatabaseSessionManager] = None):
        self.db = db_manager or get_db_session_manager()

    def calculate_next_time(self, base_time: datetime, frequency: str) -> datetime:
        """Calculates next check-in datetime based on frequency interval."""
        hours = CADENCE_HOURS_MAP.get(frequency.upper(), 24)
        return base_time + timedelta(hours=hours)

    def schedule_first_checkin(
        self,
        patient_id: str,
        care_plan_id: Optional[str] = None,
        frequency: str = "DAILY",
        start_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Schedules Day 1 check-in when a patient is activated post-discharge.
        """
        start = start_date or datetime.utcnow()
        scheduled_at = self.calculate_next_time(start, frequency)

        with self.db.session_scope() as session:
            repo = ScheduleRepository(session)
            # Cancel any existing stale pending schedules
            repo.cancel_pending_schedules(patient_id)

            sched = repo.create_schedule(
                patient_id=patient_id,
                care_plan_id=care_plan_id,
                care_day=1,
                scheduled_at=scheduled_at,
                frequency=frequency,
                status="SCHEDULED",
            )
            return {
                "schedule_id": sched.schedule_id,
                "patient_id": sched.patient_id,
                "care_day": sched.care_day,
                "scheduled_at": str(sched.scheduled_at),
                "monitoring_frequency": sched.frequency,
                "status": sched.status,
            }

    def schedule_next_checkin(
        self,
        patient_id: str,
        current_day: int,
        frequency: str,
        care_duration_days: int,
        care_plan_id: Optional[str] = None,
        base_time: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Schedules next check-in if current_day < care_duration_days.
        Stops scheduling if plan is complete.
        """
        next_day = current_day + 1
        if next_day > care_duration_days:
            # Plan duration reached -> No more routine check-ins
            return None

        now = base_time or datetime.utcnow()
        scheduled_at = self.calculate_next_time(now, frequency)

        with self.db.session_scope() as session:
            repo = ScheduleRepository(session)
            sched = repo.create_schedule(
                patient_id=patient_id,
                care_plan_id=care_plan_id,
                care_day=next_day,
                scheduled_at=scheduled_at,
                frequency=frequency,
                status="SCHEDULED",
            )
            return {
                "schedule_id": sched.schedule_id,
                "patient_id": sched.patient_id,
                "care_day": sched.care_day,
                "scheduled_at": str(sched.scheduled_at),
                "monitoring_frequency": sched.frequency,
                "status": sched.status,
            }

    def complete_current_checkin(self, patient_id: str, care_day: int) -> Optional[Dict[str, Any]]:
        """Marks a pending check-in as COMPLETED."""
        with self.db.session_scope() as session:
            repo = ScheduleRepository(session)
            pending = repo.get_pending_schedules(patient_id)
            for s in pending:
                if s.care_day == care_day:
                    updated = repo.update_schedule_status(s.schedule_id, "COMPLETED")
                    return {
                        "schedule_id": updated.schedule_id,
                        "patient_id": updated.patient_id,
                        "care_day": updated.care_day,
                        "status": updated.status,
                    }
            return None

    def cancel_pending_schedules(self, patient_id: str, reason: Optional[str] = None) -> int:
        """Cancels all pending check-ins (e.g. on readmission)."""
        with self.db.session_scope() as session:
            repo = ScheduleRepository(session)
            return repo.cancel_pending_schedules(patient_id)

    def check_missed_checkins(
        self,
        patient_id: Optional[str] = None,
        now: Optional[datetime] = None,
        grace_period_hours: int = 4,
    ) -> List[Dict[str, Any]]:
        """
        Identifies scheduled check-ins that have exceeded their grace period without submission.
        Marks them as MISSED and returns events for orchestrator ingestion.
        """
        current_time = now or datetime.utcnow()
        missed_events = []

        with self.db.session_scope() as session:
            repo = ScheduleRepository(session)
            # Find candidate patients
            if patient_id:
                pending = repo.get_pending_schedules(patient_id)
            else:
                # Query all pending
                from ..models import MonitoringSchedule
                pending = (
                    session.query(MonitoringSchedule)
                    .filter(MonitoringSchedule.status == "SCHEDULED")
                    .all()
                )

            for s in pending:
                cutoff = s.scheduled_at + timedelta(hours=grace_period_hours)
                if current_time > cutoff:
                    repo.update_schedule_status(s.schedule_id, "MISSED")
                    missed_events.append({
                        "patient_id": s.patient_id,
                        "event_type": "MISSED_CHECKIN",
                        "day": s.care_day,
                        "scheduled_at": str(s.scheduled_at),
                        "frequency": s.frequency,
                        "payload": {
                            "reason": "Scheduled check-in window expired without patient submission",
                            "care_day": s.care_day,
                        },
                    })

        return missed_events
