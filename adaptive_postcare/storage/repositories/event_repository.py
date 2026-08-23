"""
Repository for HospitalEvent entity operations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from ..models import HospitalEvent, generate_uuid


class EventRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_event(
        self,
        patient_id: str,
        event_type: str,
        hospital_id: Optional[str] = None,
        event_timestamp: Optional[datetime] = None,
        payload: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None,
    ) -> HospitalEvent:
        """Appends a new hospital event to the event stream."""
        e_type = str(event_type).strip().upper()
        event = HospitalEvent(
            event_id=event_id or generate_uuid(),
            patient_id=str(patient_id).strip(),
            hospital_id=hospital_id,
            event_type=e_type,
            event_timestamp=event_timestamp or datetime.utcnow(),
            payload=payload or {},
        )
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event

    def get_patient_events(
        self,
        patient_id: str,
        event_type: Optional[str] = None,
    ) -> List[HospitalEvent]:
        """Retrieves all hospital events for a patient."""
        query = self.session.query(HospitalEvent).filter(HospitalEvent.patient_id == patient_id)
        if event_type:
            query = query.filter(HospitalEvent.event_type == event_type.strip().upper())
        return query.order_by(HospitalEvent.event_timestamp.asc(), HospitalEvent.created_at.asc()).all()

    def get_latest_event(self, patient_id: str) -> Optional[HospitalEvent]:
        """Retrieves the most recent hospital event for a patient."""
        events = self.get_patient_events(patient_id)
        return events[-1] if events else None
