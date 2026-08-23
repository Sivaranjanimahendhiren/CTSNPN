"""
Tool 4: Medication Tool
Responsibility: Processing patient medication compliance logs and calculating updated adherence.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool

# In-memory medication history
_MEDICATION_LOG_STORE: Dict[str, list] = {}


class MedicationInput(BaseModel):
    """Input schema for Medication Tool."""
    patient_id: str = Field(..., min_length=1, description="Unique patient identifier")
    medication_taken: bool = Field(..., description="True if patient confirmed taking medication, False otherwise")
    day: int = Field(default=0, ge=0, description="Post-discharge journey day")
    missed_reason: Optional[str] = Field(default=None, description="Reported reason for missed dose if applicable")
    current_adherence: float = Field(default=1.0, ge=0.0, le=1.0, description="Baseline or previous adherence rate")


class MedicationOutput(BaseModel):
    """Output schema for Medication Tool."""
    patient_id: str = Field(...)
    day: int = Field(...)
    medication_taken: bool = Field(...)
    updated_adherence: float = Field(..., ge=0.0, le=1.0, description="Recalculated adherence rate")
    total_doses_logged: int = Field(...)
    consecutive_missed_doses: int = Field(...)
    requires_adherence_counseling: bool = Field(...)
    message: str = Field(...)


@tool(args_schema=MedicationInput)
def medication_adherence_tool(
    patient_id: str,
    medication_taken: bool,
    day: int = 0,
    missed_reason: Optional[str] = None,
    current_adherence: float = 1.0,
) -> Dict[str, Any]:
    """
    Log medication compliance response and calculate updated adherence metrics.
    """
    history = _MEDICATION_LOG_STORE.setdefault(patient_id, [])
    history.append({
        "day": day,
        "taken": medication_taken,
        "reason": missed_reason,
    })

    total_logs = len(history)
    taken_count = sum(1 for entry in history if entry["taken"])
    recalculated_adherence = round(taken_count / total_logs, 2)

    # Calculate consecutive missed doses
    consecutive_missed = 0
    for entry in reversed(history):
        if not entry["taken"]:
            consecutive_missed += 1
        else:
            break

    needs_counseling = (recalculated_adherence < 0.80) or (consecutive_missed >= 2)

    msg = "Medication adherence verified." if medication_taken else f"Missed dose logged. Reason: {missed_reason or 'None reported'}."

    output = MedicationOutput(
        patient_id=patient_id,
        day=day,
        medication_taken=medication_taken,
        updated_adherence=recalculated_adherence,
        total_doses_logged=total_logs,
        consecutive_missed_doses=consecutive_missed,
        requires_adherence_counseling=needs_counseling,
        message=msg,
    )
    return output.model_dump()
