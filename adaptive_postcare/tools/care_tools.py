"""
Care intervention and communication tools.
"""

from typing import Dict, Any
from langchain_core.tools import tool


@tool
def send_patient_notification(patient_id: str, message: str, channel: str = "IN_APP") -> Dict[str, Any]:
    """
    Send an informative or check-in message to the patient.
    """
    return {
        "status": "SENT",
        "patient_id": patient_id,
        "message": message,
        "channel": channel,
    }


@tool
def schedule_followup(patient_id: str, due_in_hours: int, purpose: str) -> Dict[str, Any]:
    """
    Schedule a future automated or clinical check-in for the patient.
    """
    return {
        "status": "SCHEDULED",
        "patient_id": patient_id,
        "due_in_hours": due_in_hours,
        "purpose": purpose,
    }


@tool
def log_intervention(patient_id: str, intervention_type: str, details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Log an executed care intervention into the patient's care trajectory audit trail.
    """
    return {
        "status": "LOGGED",
        "patient_id": patient_id,
        "intervention_type": intervention_type,
        "details": details,
    }
