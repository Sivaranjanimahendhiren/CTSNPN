"""
Tool 6: Appointment Tool
Responsibility: Scheduling and confirming clinical follow-ups, telehealth visits, and nurse calls.
"""

from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from langchain_core.tools import tool

# In-memory appointment store
_APPOINTMENT_STORE: list = []


class AppointmentInput(BaseModel):
    """Input schema for Appointment Tool."""
    patient_id: str = Field(..., min_length=1, description="Unique patient identifier")
    due_in_hours: int = Field(..., ge=1, description="Hours from now until scheduled encounter")
    purpose: str = Field(..., min_length=1, description="Clinical purpose of the appointment")
    appointment_type: str = Field(default="TELEHEALTH_VISIT", description="TELEHEALTH_VISIT, NURSE_PHONE_CHECKIN, IN_PERSON_FOLLOWUP")


class AppointmentOutput(BaseModel):
    """Output schema for Appointment Tool."""
    appointment_id: str = Field(...)
    patient_id: str = Field(...)
    appointment_type: str = Field(...)
    due_in_hours: int = Field(...)
    purpose: str = Field(...)
    status: str = Field(default="CONFIRMED")
    booking_timestamp: str = Field(...)


@tool(args_schema=AppointmentInput)
def appointment_scheduling_tool(
    patient_id: str,
    due_in_hours: int,
    purpose: str,
    appointment_type: str = "TELEHEALTH_VISIT"
) -> Dict[str, Any]:
    """
    Schedule a clinical follow-up appointment or nurse check-in call.
    """
    appointment_id = f"APT-{patient_id}-{len(_APPOINTMENT_STORE) + 1:04d}"
    now_iso = datetime.utcnow().isoformat()

    record = AppointmentOutput(
        appointment_id=appointment_id,
        patient_id=patient_id,
        appointment_type=appointment_type.upper(),
        due_in_hours=due_in_hours,
        purpose=purpose,
        status="CONFIRMED",
        booking_timestamp=now_iso,
    )
    _APPOINTMENT_STORE.append(record.model_dump())
    return record.model_dump()
