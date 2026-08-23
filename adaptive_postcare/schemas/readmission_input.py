"""
Input Schema 1: Initial Risk Event payload from the external readmission prediction model.
"""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class RiskLevelEnum(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class InitialRiskEvent(BaseModel):
    """
    Schema for INPUT 1: INITIAL_RISK_EVENT.
    Received from the external readmission model at the start of patient post-care.
    """
    patient_id: str = Field(..., min_length=1, description="Unique identifier for the patient")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Readmission probability score (0.0 to 1.0)")
    risk_level: RiskLevelEnum = Field(..., description="Risk category: LOW, MEDIUM, HIGH, CRITICAL")
    care_duration_days: int = Field(default=30, ge=1, description="Assigned post-care duration in days (flexible, not fixed)")
    recommended_care_days: Optional[int] = Field(
        default=None,
        description="Care duration in days recommended by the readmission model"
    )
    model_version: Optional[str] = Field(default="readmission-v1", description="Version identifier of the external ML model")
    model_metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Optional metadata or feature contributions from external ML model"
    )

    @field_validator("patient_id", mode="before")
    @classmethod
    def validate_patient_id(cls, v: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("patient_id must be a non-empty string")
        return v.strip()

    @field_validator("risk_level", mode="before")
    @classmethod
    def validate_risk_level(cls, v: Any) -> RiskLevelEnum:
        if isinstance(v, RiskLevelEnum):
            return v
        if isinstance(v, str):
            cleaned = v.strip().upper()
            try:
                return RiskLevelEnum(cleaned)
            except ValueError:
                valid_options = [e.value for e in RiskLevelEnum]
                raise ValueError(f"Invalid risk_level: '{v}'. Must be one of {valid_options}")
        raise ValueError(f"risk_level must be a string or RiskLevelEnum, got {type(v)}")

    @field_validator("care_duration_days", mode="before")
    @classmethod
    def validate_care_duration(cls, v: Any) -> int:
        if not isinstance(v, int) or isinstance(v, bool):
            try:
                v_int = int(v)
            except (ValueError, TypeError):
                raise ValueError(f"care_duration_days must be an integer, got {v}")
            v = v_int
        if v < 1:
            raise ValueError(f"care_duration_days must be >= 1, got {v}")
        return v

    @model_validator(mode="after")
    def synchronize_care_duration(self) -> "InitialRiskEvent":
        if self.recommended_care_days is not None:
            if self.recommended_care_days < 1:
                raise ValueError(f"recommended_care_days must be >= 1, got {self.recommended_care_days}")
            # Align care_duration_days with recommended_care_days
            self.care_duration_days = self.recommended_care_days
        else:
            self.recommended_care_days = self.care_duration_days
        return self


# Backward compatibility alias
ReadmissionModelInput = InitialRiskEvent
