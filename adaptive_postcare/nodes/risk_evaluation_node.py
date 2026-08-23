"""
Node 3: Risk Evaluation
Responsibility:
- Evaluate patient condition using:
  1. baseline risk score
  2. baseline risk level
  3. current symptoms
  4. medication adherence
  5. feedback history
  6. data quality
  7. trends
- Updates escalation_required flag without modifying or retraining the external readmission model
"""

from typing import Any, Dict
from ..state.patient_state import PatientState
from ..policies.escalation_policies import check_escalation_triggers


def risk_evaluation_node(state: PatientState) -> Dict[str, Any]:
    """
    Step 3: Risk Evaluation
    Assesses clinical risk and determines if escalation or intervention adjustments are required.
    """
    symptoms = state.get("symptoms", [])
    risk_level = state.get("risk_level", "LOW")
    risk_score = state.get("risk_score", 0.0)
    adherence = state.get("medication_adherence", 1.0)
    data_quality = state.get("data_quality", "GOOD")
    feedback_history = state.get("feedback_history", [])

    # Check for abnormal vitals if available in latest event
    event = state.get("current_event") or {}
    feedback_data = event.get("feedback", {})
    vitals_abnormal = False
    if isinstance(feedback_data, dict):
        systolic = feedback_data.get("systolic_bp") or feedback_data.get("systolic")
        if systolic and (systolic > 160 or systolic < 90):
            vitals_abnormal = True

    escalation_decision = check_escalation_triggers(
        symptoms=symptoms,
        risk_level=risk_level,
        medication_adherence=adherence,
        data_quality=data_quality,
        feedback_history=feedback_history,
        vitals_abnormal=vitals_abnormal,
    )

    return {
        "escalation_required": escalation_decision.should_escalate,
    }
