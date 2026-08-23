"""
Alerting and clinical escalation tools.
"""

from typing import Dict, Any
from langchain_core.tools import tool


@tool
def alert_care_team(patient_id: str, reason: str, priority: str = "HIGH") -> Dict[str, Any]:
    """
    Alert the assigned hospital care team / primary nurse about a clinical issue.
    """
    return {
        "status": "SUCCESS",
        "action": "ALERT_CARE_TEAM",
        "patient_id": patient_id,
        "reason": reason,
        "priority": priority,
    }


@tool
def alert_emergency_services(patient_id: str, details: str) -> Dict[str, Any]:
    """
    Trigger immediate emergency intervention protocol for life-threatening events.
    """
    return {
        "status": "TRIGGERED",
        "action": "EMERGENCY_ESCALATION",
        "patient_id": patient_id,
        "details": details,
    }
