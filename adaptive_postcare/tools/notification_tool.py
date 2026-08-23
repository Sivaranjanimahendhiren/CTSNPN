"""
Tool 3: Check-in / Notification Tool
Responsibility: Delivering patient check-in reminders, surveys, and messages.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool

# In-memory notification log
_NOTIFICATION_OUTBOX: list = []


class CheckinNotificationInput(BaseModel):
    """Input schema for Check-in / Notification Tool."""
    patient_id: str = Field(..., min_length=1, description="Unique patient identifier")
    day: int = Field(..., ge=0, description="Current day of post-care journey")
    message: str = Field(..., min_length=1, description="Check-in or alert message to deliver")
    channel: str = Field(default="IN_APP", description="Delivery channel: IN_APP, SMS, EMAIL, PHONE")


class CheckinNotificationOutput(BaseModel):
    """Output schema for Check-in / Notification Tool."""
    notification_id: str = Field(...)
    patient_id: str = Field(...)
    day: int = Field(...)
    channel: str = Field(...)
    status: str = Field(default="DELIVERED", description="DELIVERED, QUEUED, FAILED")
    message_sent: str = Field(...)
    timestamp: str = Field(...)


@tool(args_schema=CheckinNotificationInput)
def checkin_notification_tool(
    patient_id: str,
    day: int,
    message: str,
    channel: str = "IN_APP"
) -> Dict[str, Any]:
    """
    Send an automated check-in reminder or clinical message to the patient.
    """
    notification_id = f"NOTIF-{patient_id}-{day}-{len(_NOTIFICATION_OUTBOX) + 1:04d}"
    now_iso = datetime.utcnow().isoformat()

    record = CheckinNotificationOutput(
        notification_id=notification_id,
        patient_id=patient_id,
        day=day,
        channel=channel.upper(),
        status="DELIVERED",
        message_sent=message,
        timestamp=now_iso,
    )
    _NOTIFICATION_OUTBOX.append(record.model_dump())
    return record.model_dump()
