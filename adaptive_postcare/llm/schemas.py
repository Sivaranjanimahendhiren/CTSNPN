"""
Structured output Pydantic schemas for LLM responses.
Ensures every model output is strictly typed and validated before being consumed by nodes.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ClinicalFeedbackAnalysis(BaseModel):
    """
    Structured output schema for LLM interpretation in the Understand node.
    """
    symptom_status: str = Field(
        default="stable",
        description="Categorical progression: improving, stable, worsening, resolved, unknown"
    )
    extracted_symptoms: List[str] = Field(
        default_factory=list,
        description="Explicit extracted symptom tokens (e.g. ['dizziness', 'cough'])"
    )
    medication_status: str = Field(
        default="adherent",
        description="Adherence classification: adherent, non_adherent, unknown"
    )
    data_quality: str = Field(
        default="high",
        description="Assessment of patient response clarity: high, medium, low, incomplete"
    )
    concerns: List[str] = Field(
        default_factory=list,
        description="Non-diagnostic observational notes or reported friction"
    )
    confidence: float = Field(
        default=0.90,
        ge=0.0,
        le=1.0,
        description="Model confidence score in the interpretation (0.0 to 1.0)"
    )

    @field_validator("symptom_status", mode="before")
    @classmethod
    def normalize_symptom_status(cls, v: str) -> str:
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if v_clean in ["improving", "stable", "worsening", "resolved", "unknown"]:
                return v_clean
        return "stable"

    @field_validator("medication_status", mode="before")
    @classmethod
    def normalize_medication_status(cls, v: str) -> str:
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if v_clean in ["adherent", "non_adherent", "unknown"]:
                return v_clean
        return "unknown"

    @field_validator("data_quality", mode="before")
    @classmethod
    def normalize_data_quality(cls, v: str) -> str:
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if v_clean in ["high", "medium", "low", "incomplete", "good", "degraded", "poor"]:
                return v_clean
        return "high"


class AdaptationReasoning(BaseModel):
    """
    Structured output schema for LLM qualitative reasoning in the Adapt node.
    """
    qualitative_summary: str = Field(
        ...,
        description="Concise summary of patient trajectory and response patterns"
    )
    observed_barriers: List[str] = Field(
        default_factory=list,
        description="Reported barriers to compliance, access, or recovery"
    )
    suggested_focus_area: Optional[str] = Field(
        default=None,
        description="Recommended non-clinical engagement focus (e.g. hydration, rest, pill reminder timing)"
    )
    confidence: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Model confidence score in the reasoning (0.0 to 1.0)"
    )
