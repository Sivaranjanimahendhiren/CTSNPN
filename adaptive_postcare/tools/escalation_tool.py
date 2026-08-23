"""
Tool 7: Escalation Tool
Responsibility: Dispatching emergency and urgent escalation notifications to clinical care teams.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from langchain_core.tools import tool

# In-memory escalation audit trail
_ESCALATION_DISPATCH_LOG: list = []


class EscalationInput(BaseModel):
    """Input schema for Escalation Tool."""
    patient_id: str = Field(..., min_length=1, description="Unique patient identifier")
    reason: str = Field(..., min_length=1, description="Clinical rationale for escalation")
    priority: str = Field(default="HIGH", description="Priority level: NORMAL, HIGH, EMERGENCY")
    symptoms: Optional[List[str]] = Field(default=None, description="Active red-flag symptoms detected")


class EscalationOutput(BaseModel):
    """Output schema for Escalation Tool."""
    escalation_id: str = Field(...)
    patient_id: str = Field(...)
    reason: str = Field(...)
    priority: str = Field(...)
    target_team: str = Field(...)
    sla_response_minutes: int = Field(...)
    dispatch_timestamp: str = Field(...)
    status: str = Field(default="DISPATCHED")


@tool(args_schema=EscalationInput)
def clinical_escalation_tool(
    patient_id: str,
    reason: str,
    priority: str = "HIGH",
    symptoms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Dispatch an immediate clinical escalation to on-call medical staff.
    """
    prio_upper = priority.strip().upper()
    escalation_id = f"ESC-{patient_id}-{len(_ESCALATION_DISPATCH_LOG) + 1:04d}"
    now_iso = datetime.utcnow().isoformat()

    if prio_upper == "EMERGENCY":
        target = "EMERGENCY_RAPID_RESPONSE_TEAM"
        sla = 15
    elif prio_upper == "HIGH":
        target = "ON_CALL_CARE_COORDINATOR"
        sla = 30
    else:
        target = "TRIAGE_NURSE_POOL"
        sla = 60

    record = EscalationOutput(
        escalation_id=escalation_id,
        patient_id=patient_id,
        reason=reason,
        priority=prio_upper,
        target_team=target,
        sla_response_minutes=sla,
        dispatch_timestamp=now_iso,
        status="DISPATCHED",
    )
    _ESCALATION_DISPATCH_LOG.append(record.model_dump())
    return record.model_dump()
