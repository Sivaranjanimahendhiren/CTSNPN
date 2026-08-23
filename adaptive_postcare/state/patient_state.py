"""
Patient State management and validation for the Adaptive Agentic Post-Care System.
Supports state persistence and evolution across multiple patient events.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from typing_extensions import TypedDict
from pydantic import BaseModel, Field, field_validator, model_validator


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PlanStatus(str, Enum):
    INITIALIZED = "INITIALIZED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ESCALATED = "ESCALATED"
    COMPLETED = "COMPLETED"
    DISCHARGED = "DISCHARGED"


class DataQuality(str, Enum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    POOR = "POOR"
    INCOMPLETE = "INCOMPLETE"


class MonitoringFrequency(str, Enum):
    HOURLY_6 = "HOURLY_6"
    HOURLY_12 = "HOURLY_12"
    DAILY = "DAILY"
    TWICE_DAILY = "TWICE_DAILY"
    WEEKLY = "WEEKLY"
    ADAPTIVE = "ADAPTIVE"


class CareAction(str, Enum):
    CONTINUE = "CONTINUE"
    INCREASE_MONITORING = "INCREASE_MONITORING"
    DECREASE_MONITORING = "DECREASE_MONITORING"
    REQUEST_MORE_DATA = "REQUEST_MORE_DATA"
    MODIFY_CARE_PLAN = "MODIFY_CARE_PLAN"
    ESCALATE = "ESCALATE"
    COMPLETE = "COMPLETE"


class ActionRecord(BaseModel):
    """Structured representation of an action executed or planned."""
    action_type: str = Field(..., min_length=1, description="Identifier of the action")
    details: Dict[str, Any] = Field(default_factory=dict, description="Metadata or parameters for the action")
    timestamp: Optional[str] = Field(default=None, description="ISO timestamp of when action occurred")
    status: str = Field(default="PENDING", description="PENDING, EXECUTED, FAILED, SKIPPED")


class PatientFeedbackItem(BaseModel):
    """Structured representation of patient feedback."""
    day: int = Field(..., ge=0, description="Day of post-care the feedback was submitted")
    content: str = Field(..., min_length=1, description="Feedback message or response summary")
    sentiment: Optional[str] = Field(default="NEUTRAL", description="POSITIVE, NEUTRAL, NEGATIVE, DISTRESSED")
    barrier_reported: Optional[str] = Field(default=None, description="Any reported barrier (e.g., cost, side effects)")


class PatientStateModel(BaseModel):
    """
    Strongly validated Pydantic model for PatientState.
    Preserves and governs patient state across multiple post-care events.
    """
    # Core Patient & External ML Model Initializers (Not fixed to 30 days)
    patient_id: str = Field(..., min_length=1, description="Unique patient identifier")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Readmission risk score (0.0 to 1.0) from external model")
    risk_level: RiskLevel = Field(..., description="Categorical risk tier: LOW, MEDIUM, HIGH, CRITICAL")
    care_duration_days: int = Field(..., ge=1, description="Assigned post-care duration in days (flexible, not fixed)")

    # Temporal & Cadence Tracking
    current_day: int = Field(default=0, ge=0, description="Current day into post-care journey (0 <= current_day <= care_duration_days)")
    last_checkin_day: Optional[int] = Field(default=None, ge=0, description="Most recent day patient submitted check-in")
    monitoring_frequency: MonitoringFrequency = Field(default=MonitoringFrequency.DAILY, description="Dynamic monitoring cadence")

    # Clinical & Adherence Attributes
    care_plan: Dict[str, Any] = Field(default_factory=dict, description="Current active care regimen and instructions")
    symptoms: List[str] = Field(default_factory=list, description="Active symptoms reported or detected")
    medication_adherence: float = Field(default=1.0, ge=0.0, le=1.0, description="Adherence rate (0.0 to 1.0)")
    data_quality: DataQuality = Field(default=DataQuality.GOOD, description="Quality and completeness score of reported data")

    # Current Event Ingestion
    current_event: Optional[Dict[str, Any]] = Field(default=None, description="Latest event payload being processed in graph")

    # Actions & Escalation
    current_action: Optional[Union[Dict[str, Any], str]] = Field(default=None, description="Action currently in progress")
    next_action: Optional[Union[Dict[str, Any], str]] = Field(default=None, description="Next planned action")
    escalation_required: bool = Field(default=False, description="Flag indicating immediate clinical staff escalation needed")
    previous_actions: List[Dict[str, Any]] = Field(default_factory=list, description="Historical log of executed actions")

    # Feedback History & Lifecycle
    latest_feedback: Optional[Union[Dict[str, Any], str]] = Field(default=None, description="Most recent patient feedback")
    feedback_history: List[Dict[str, Any]] = Field(default_factory=list, description="Chronological feedback entries")
    adaptation_notes: List[str] = Field(default_factory=list, description="Notes on adaptations made to care plan")
    plan_status: PlanStatus = Field(default=PlanStatus.INITIALIZED, description="Current operational status of care plan")

    @field_validator("risk_level", mode="before")
    @classmethod
    def validate_risk_level(cls, v: Any) -> RiskLevel:
        if isinstance(v, RiskLevel):
            return v
        if isinstance(v, str):
            v_upper = v.strip().upper()
            try:
                return RiskLevel(v_upper)
            except ValueError:
                raise ValueError(f"Invalid risk_level: '{v}'. Must be one of {[e.value for e in RiskLevel]}")
        raise ValueError(f"risk_level must be a string or RiskLevel enum, got {type(v)}")

    @field_validator("plan_status", mode="before")
    @classmethod
    def validate_plan_status(cls, v: Any) -> PlanStatus:
        if isinstance(v, PlanStatus):
            return v
        if isinstance(v, str):
            v_upper = v.strip().upper()
            try:
                return PlanStatus(v_upper)
            except ValueError:
                raise ValueError(f"Invalid plan_status: '{v}'. Must be one of {[e.value for e in PlanStatus]}")
        raise ValueError(f"plan_status must be a string or PlanStatus enum, got {type(v)}")

    @field_validator("monitoring_frequency", mode="before")
    @classmethod
    def validate_monitoring_frequency(cls, v: Any) -> MonitoringFrequency:
        if isinstance(v, MonitoringFrequency):
            return v
        if isinstance(v, str):
            v_upper = v.strip().upper()
            try:
                return MonitoringFrequency(v_upper)
            except ValueError:
                raise ValueError(f"Invalid monitoring_frequency: '{v}'. Must be one of {[e.value for e in MonitoringFrequency]}")
        raise ValueError(f"monitoring_frequency must be a string or MonitoringFrequency enum, got {type(v)}")

    @field_validator("data_quality", mode="before")
    @classmethod
    def validate_data_quality(cls, v: Any) -> DataQuality:
        if isinstance(v, DataQuality):
            return v
        if isinstance(v, str):
            v_upper = v.strip().upper()
            try:
                return DataQuality(v_upper)
            except ValueError:
                raise ValueError(f"Invalid data_quality: '{v}'. Must be one of {[e.value for e in DataQuality]}")
        raise ValueError(f"data_quality must be a string or DataQuality enum, got {type(v)}")

    @model_validator(mode="after")
    def validate_state_invariants(self) -> "PatientStateModel":
        if self.care_duration_days <= 0:
            raise ValueError(f"care_duration_days must be >= 1, got {self.care_duration_days}")

        if self.current_day > self.care_duration_days:
            raise ValueError(
                f"current_day ({self.current_day}) cannot exceed care_duration_days ({self.care_duration_days})"
            )

        if self.last_checkin_day is not None and self.last_checkin_day > self.current_day:
            raise ValueError(
                f"last_checkin_day ({self.last_checkin_day}) cannot exceed current_day ({self.current_day})"
            )

        return self

    @classmethod
    def initialize_from_external_model(
        cls,
        patient_id: str,
        risk_score: float,
        risk_level: Union[RiskLevel, str],
        care_duration_days: int,
        initial_care_plan: Optional[Dict[str, Any]] = None,
    ) -> "PatientStateModel":
        r_level = risk_level if isinstance(risk_level, RiskLevel) else RiskLevel(risk_level.strip().upper())
        if r_level == RiskLevel.CRITICAL:
            default_freq = MonitoringFrequency.HOURLY_6
        elif r_level == RiskLevel.HIGH:
            default_freq = MonitoringFrequency.HOURLY_12
        elif r_level == RiskLevel.MEDIUM:
            default_freq = MonitoringFrequency.TWICE_DAILY
        else:
            default_freq = MonitoringFrequency.DAILY

        return cls(
            patient_id=patient_id,
            risk_score=risk_score,
            risk_level=r_level,
            care_duration_days=care_duration_days,
            current_day=0,
            monitoring_frequency=default_freq,
            care_plan=initial_care_plan or {},
            symptoms=[],
            medication_adherence=1.0,
            data_quality=DataQuality.GOOD,
            current_event=None,
            current_action=None,
            next_action=CareAction.CONTINUE.value,
            escalation_required=(r_level == RiskLevel.CRITICAL),
            previous_actions=[],
            latest_feedback=None,
            feedback_history=[],
            adaptation_notes=[],
            last_checkin_day=None,
            plan_status=PlanStatus.INITIALIZED,
        )

    def to_state_dict(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["risk_level"] = self.risk_level.value
        data["plan_status"] = self.plan_status.value
        data["data_quality"] = self.data_quality.value
        data["monitoring_frequency"] = self.monitoring_frequency.value
        return data


class PatientState(TypedDict, total=False):
    """
    LangGraph TypedDict schema representing patient state across graph nodes and events.
    """
    patient_id: str
    risk_score: float
    risk_level: str
    care_duration_days: int
    current_day: int
    monitoring_frequency: str
    care_plan: Dict[str, Any]
    symptoms: List[str]
    latest_feedback: Optional[Union[Dict[str, Any], str]]
    data_quality: str
    medication_adherence: float
    current_event: Optional[Dict[str, Any]]
    current_action: Optional[Union[Dict[str, Any], str]]
    next_action: Optional[Union[Dict[str, Any], str]]
    escalation_required: bool
    previous_actions: List[Dict[str, Any]]
    feedback_history: List[Dict[str, Any]]
    adaptation_notes: List[str]
    last_checkin_day: Optional[int]
    plan_status: str
