"""
Tool 2: Care Plan Tool
Responsibility: In-memory retrieval and modification of active care plans.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool

# In-memory care plan store
_CARE_PLAN_STORE: Dict[str, Dict[str, Any]] = {}


class CarePlanInput(BaseModel):
    """Input schema for Care Plan Tool."""
    patient_id: str = Field(..., min_length=1, description="Unique patient identifier")
    action: str = Field(default="GET", description="Operation: 'GET', 'SET', or 'MODIFY'")
    plan_data: Optional[Dict[str, Any]] = Field(default=None, description="Care plan payload or updates")


class CarePlanOutput(BaseModel):
    """Output schema for Care Plan Tool."""
    status: str = Field(..., description="SUCCESS or NOT_FOUND")
    patient_id: str = Field(...)
    action_performed: str = Field(...)
    care_plan: Dict[str, Any] = Field(default_factory=dict)
    message: str = Field(...)


@tool(args_schema=CarePlanInput)
def care_plan_tool(
    patient_id: str,
    action: str = "GET",
    plan_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Retrieve, create, or update the active care plan for a patient.
    """
    act = action.strip().upper()

    if act in ["SET", "MODIFY"] and plan_data:
        existing = _CARE_PLAN_STORE.get(patient_id, {})
        existing.update(plan_data)
        _CARE_PLAN_STORE[patient_id] = existing
        return CarePlanOutput(
            status="SUCCESS",
            patient_id=patient_id,
            action_performed=act,
            care_plan=existing,
            message=f"Care plan {act.lower()}ed successfully"
        ).model_dump()
    else:
        existing = _CARE_PLAN_STORE.get(patient_id, {
            "patient_id": patient_id,
            "status": "DEFAULT_INITIALIZED",
            "monitoring_frequency": "DAILY",
        })
        return CarePlanOutput(
            status="SUCCESS",
            patient_id=patient_id,
            action_performed="GET",
            care_plan=existing,
            message="Active care plan retrieved"
        ).model_dump()
