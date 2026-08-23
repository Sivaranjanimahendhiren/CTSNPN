"""
Input Schema 2: Patient Event payload received during the post-care journey.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class EventTypeEnum(str, Enum):
    DAILY_CHECKIN = "daily_checkin"
    SYMPTOM_REPORT = "symptom_report"
    MEDICATION_LOG = "medication_log"
    VITALS_SUBMISSION = "vitals_submission"
    MISSED_CHECKIN = "missed_checkin"
    CLINICAL_QUERY = "clinical_query"
    EMERGENCY_ALERT = "emergency_alert"
    # Hospital Event Stream Types
    PATIENT_ADMITTED = "patient_admitted"
    PATIENT_DISCHARGED = "patient_discharged"
    PATIENT_READMITTED = "patient_readmitted"
    CONSULTATION_COMPLETED = "consultation_completed"
    APPOINTMENT_CREATED = "appointment_created"
    APPOINTMENT_MISSED = "appointment_missed"


class CheckinFeedback(BaseModel):
    """
    Structured feedback payload submitted during patient check-in or events.
    """
    model_config = ConfigDict(extra="allow")

    symptoms: Optional[Union[str, List[str]]] = Field(
        default=None,
        description="Reported symptoms or status description (e.g. 'improving', 'mild fever')"
    )
    medication_taken: Optional[bool] = Field(
        default=None,
        description="Whether prescribed medication was taken"
    )
    energy_level: Optional[int] = Field(
        default=None,
        ge=1,
        le=10,
        description="Self-reported energy or pain scale (1-10)"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Free-text feedback or remarks"
    )


class PatientEvent(BaseModel):
    """
    Schema for INPUT 2: PATIENT_EVENT.
    Received during the post-discharge care journey and hospital event stream.
    """
    patient_id: str = Field(..., min_length=1, description="Unique identifier for the patient")
    hospital_id: Optional[str] = Field(default=None, description="Optional hospital identifier")
    event_type: Union[EventTypeEnum, str] = Field(
        default=EventTypeEnum.DAILY_CHECKIN,
        description="Type of event (e.g., 'daily_checkin', 'patient_discharged')"
    )
    day: int = Field(default=0, ge=0, description="The care journey day on which this event occurred")
    event_timestamp: Optional[Any] = Field(default=None, description="ISO timestamp of when the event occurred")
    feedback: Union[CheckinFeedback, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Event payload containing symptoms, medication adherence, energy level, etc."
    )
    payload: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional alias for feedback payload"
    )

    @field_validator("patient_id", mode="before")
    @classmethod
    def validate_patient_id(cls, v: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("patient_id must be a non-empty string")
        return v.strip()

    @field_validator("event_type", mode="before")
    @classmethod
    def validate_event_type(cls, v: Any) -> Union[EventTypeEnum, str]:
        if isinstance(v, EventTypeEnum):
            return v
        if isinstance(v, str):
            v_cleaned = v.strip().lower()
            try:
                return EventTypeEnum(v_cleaned)
            except ValueError:
                # Allow custom string event types if normalized
                return v_cleaned
        raise ValueError(f"event_type must be a string or EventTypeEnum, got {type(v)}")

    @field_validator("day", mode="before")
    @classmethod
    def validate_day(cls, v: Any) -> int:
        if not isinstance(v, int) or isinstance(v, bool):
            try:
                v_int = int(v)
            except (ValueError, TypeError):
                raise ValueError(f"day must be an integer, got {v}")
            v = v_int
        if v < 0:
            raise ValueError(f"day cannot be negative, got {v}")
        return v

    @field_validator("feedback", mode="before")
    @classmethod
    def validate_feedback(cls, v: Any) -> Union[CheckinFeedback, Dict[str, Any]]:
        if isinstance(v, CheckinFeedback):
            return v
        if isinstance(v, dict):
            return CheckinFeedback(**v)
    @model_validator(mode="after")
    def synchronize_payload_and_feedback(self) -> "PatientEvent":
        if self.payload and (not self.feedback or self.feedback == CheckinFeedback()):
            if isinstance(self.payload, dict):
                try:
                    self.feedback = CheckinFeedback(**self.payload)
                except Exception:
                    self.feedback = self.payload
        return self

    def get_symptoms_list(self) -> List[str]:
        """Utility to extract symptoms as a uniform list of strings."""
        if isinstance(self.feedback, CheckinFeedback):
            s = self.feedback.symptoms
        else:
            s = self.feedback.get("symptoms")

        if not s:
            return []
        if isinstance(s, str):
            return [s.strip()]
        if isinstance(s, list):
            return [str(item).strip() for item in s if str(item).strip()]
        return [str(s)]
