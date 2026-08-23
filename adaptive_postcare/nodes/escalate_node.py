"""
Escalate Node: Handles dedicated urgent escalation procedures and emergency notifications.
"""

from typing import Any, Dict, List
from ..state.patient_state import PatientState, PlanStatus, MonitoringFrequency
from ..tools.alert_tools import alert_care_team, alert_emergency_services


def escalate_node(state: PatientState) -> Dict[str, Any]:
    """
    Escalation Action / Tool execution node.
    Fires high-priority clinician notifications and transitions state to ESCALATED.
    """
    patient_id = state.get("patient_id", "UNKNOWN")
    symptoms = state.get("symptoms", [])
    current_day = state.get("current_day", 0)
    previous_actions: List[Dict[str, Any]] = list(state.get("previous_actions", []))

    # Check for acute red flags for emergency escalation
    is_emergency = any("chest pain" in s.lower() or "shortness of breath" in s.lower() for s in symptoms)

    if is_emergency:
        res = alert_emergency_services.invoke({
            "patient_id": patient_id,
            "details": f"Urgent red-flag symptom detected on Day {current_day}: {', '.join(symptoms)}"
        })
    else:
        res = alert_care_team.invoke({
            "patient_id": patient_id,
            "reason": f"Clinical escalation on Day {current_day} for symptoms: {', '.join(symptoms)}",
            "priority": "HIGH"
        })

    previous_actions.append({
        "action": "ESCALATION_DISPATCHED",
        "day": current_day,
        "result": res,
        "status": "EXECUTED",
    })

    return {
        "escalation_flag": True,
        "plan_status": PlanStatus.ESCALATED.value,
        "monitoring_frequency": MonitoringFrequency.HOURLY_6.value,
        "previous_actions": previous_actions,
    }
