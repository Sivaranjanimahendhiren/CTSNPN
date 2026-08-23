"""
Tool 1: Patient State Tool
Responsibility: In-memory retrieval and updating of structured patient state records.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool

# In-memory mock patient state store
_PATIENT_STATE_STORE: Dict[str, Dict[str, Any]] = {}


class PatientStateInput(BaseModel):
    """Input schema for Patient State Tool."""
    patient_id: str = Field(..., min_length=1, description="Unique patient identifier")
    action: str = Field(default="GET", description="Operation: 'GET' or 'UPDATE'")
    state_updates: Optional[Dict[str, Any]] = Field(default=None, description="Fields to update in patient state")


class PatientStateOutput(BaseModel):
    """Output schema for Patient State Tool."""
    status: str = Field(..., description="SUCCESS or ERROR")
    patient_id: str = Field(...)
    action_performed: str = Field(...)
    state_data: Dict[str, Any] = Field(default_factory=dict, description="Current or updated patient state")
    message: Optional[str] = Field(default=None)


@tool(args_schema=PatientStateInput)
def patient_state_tool(
    patient_id: str,
    action: str = "GET",
    state_updates: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Query or update in-memory patient state records.
    """
    act = action.strip().upper()
    current_state = _PATIENT_STATE_STORE.setdefault(patient_id, {
        "patient_id": patient_id,
        "risk_level": "LOW",
        "current_day": 0,
        "care_duration_days": 30,
        "symptoms": [],
        "medication_adherence": 1.0,
    })

    if act == "UPDATE" and state_updates:
        current_state.update(state_updates)
        _PATIENT_STATE_STORE[patient_id] = current_state
        return PatientStateOutput(
            status="SUCCESS",
            patient_id=patient_id,
            action_performed="UPDATE",
            state_data=current_state,
            message="Patient state updated successfully"
        ).model_dump()
    else:
        return PatientStateOutput(
            status="SUCCESS",
            patient_id=patient_id,
            action_performed="GET",
            state_data=current_state,
            message="Patient state retrieved successfully"
        ).model_dump()
