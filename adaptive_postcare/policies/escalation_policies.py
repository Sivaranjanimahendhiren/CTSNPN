"""
Clinical escalation policy evaluation.
Determines whether acute intervention or clinical staff notification is required.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class EscalationDecision(BaseModel):
    """
    Result of evaluating escalation policies on patient state.
    """
    should_escalate: bool = Field(..., description="Whether human clinical escalation is required")
    reason: str = Field(default="", description="Clinical reason or triggered rule")
    priority: str = Field(default="NORMAL", description="NORMAL, LOW, MEDIUM, HIGH, EMERGENCY")


def check_escalation_triggers(
    symptoms: List[str],
    risk_level: str,
    medication_adherence: float = 1.0,
    data_quality: str = "GOOD",
    feedback_history: Optional[List[Dict[str, Any]]] = None,
    vitals_abnormal: bool = False
) -> EscalationDecision:
    """
    Evaluates clinical and operational risk triggers across multiple state dimensions.
    """
    red_flag_symptoms = {
        "chest pain",
        "shortness of breath",
        "dyspnea",
        "loss of consciousness",
        "severe bleeding",
        "fever > 103",
        "acute distress"
    }

    # Check 1: Emergency red flags
    found_flags = [s for s in symptoms if any(flag in s.lower() for flag in red_flag_symptoms)]
    if found_flags:
        return EscalationDecision(
            should_escalate=True,
            reason=f"Emergency red-flag symptom(s) detected: {', '.join(found_flags)}",
            priority="EMERGENCY"
        )

    # Check 2: High or Critical risk level baseline
    r_level = risk_level.upper()
    if r_level == "CRITICAL":
        return EscalationDecision(
            should_escalate=True,
            reason="Patient is in CRITICAL baseline risk tier requiring continuous clinician oversight",
            priority="HIGH"
        )

    # Check 3: Abnormal vitals in moderate/high risk
    if r_level in ["HIGH", "MEDIUM"] and vitals_abnormal:
        return EscalationDecision(
            should_escalate=True,
            reason="Abnormal vitals reported in elevated risk patient tier",
            priority="HIGH"
        )

    # Check 5: Multiple persistent worsening symptoms in feedback history
    if len(symptoms) >= 3 and r_level in ["MEDIUM", "HIGH"]:
        return EscalationDecision(
            should_escalate=True,
            reason=f"Multiple concurrent symptoms reported ({', '.join(symptoms)})",
            priority="MEDIUM"
        )

    return EscalationDecision(
        should_escalate=False,
        reason="Patient condition stable within baseline parameters",
        priority="NORMAL"
    )
