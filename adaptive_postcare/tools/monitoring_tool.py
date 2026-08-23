"""
Tool 5: Monitoring Tool
Responsibility: Ingesting vitals data, evaluating physiological thresholds, and adjusting monitoring cadence.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool

# In-memory vitals log
_VITALS_STORE: Dict[str, list] = {}


class MonitoringInput(BaseModel):
    """Input schema for Monitoring Tool."""
    patient_id: str = Field(..., min_length=1, description="Unique patient identifier")
    vitals_data: Dict[str, Any] = Field(default_factory=dict, description="Dictionary of reported vitals e.g. blood_pressure, heart_rate, temp")
    day: int = Field(default=0, ge=0)
    target_frequency: Optional[str] = Field(default=None, description="Optional frequency adjustment: HOURLY_6, HOURLY_12, TWICE_DAILY, DAILY")


class MonitoringOutput(BaseModel):
    """Output schema for Monitoring Tool."""
    patient_id: str = Field(...)
    day: int = Field(...)
    vitals_logged: Dict[str, Any] = Field(...)
    abnormal_vitals_detected: bool = Field(...)
    abnormal_readings: Dict[str, str] = Field(default_factory=dict)
    active_monitoring_frequency: str = Field(...)
    status: str = Field(default="RECORDED")


@tool(args_schema=MonitoringInput)
def monitoring_cadence_tool(
    patient_id: str,
    vitals_data: Dict[str, Any],
    day: int = 0,
    target_frequency: Optional[str] = None
) -> Dict[str, Any]:
    """
    Log reported vitals and check for critical physiological bounds.
    """
    history = _VITALS_STORE.setdefault(patient_id, [])
    history.append({"day": day, "vitals": vitals_data})

    abnormal_flags: Dict[str, str] = {}

    # Check Systolic Blood Pressure
    systolic = vitals_data.get("systolic") or vitals_data.get("systolic_bp")
    if systolic is not None:
        if systolic > 160:
            abnormal_flags["systolic"] = f"Hypertensive urgency: {systolic} mmHg (>160)"
        elif systolic < 90:
            abnormal_flags["systolic"] = f"Hypotension: {systolic} mmHg (<90)"

    # Check Oxygen Saturation
    spo2 = vitals_data.get("spo2") or vitals_data.get("oxygen_saturation")
    if spo2 is not None and spo2 < 92:
        abnormal_flags["spo2"] = f"Hypoxia: {spo2}% (<92%)"

    # Check Temperature
    temp = vitals_data.get("temperature") or vitals_data.get("temp")
    if temp is not None and temp > 101.5:
        abnormal_flags["temperature"] = f"Fever: {temp} F (>101.5)"

    has_abnormal = len(abnormal_flags) > 0
    active_freq = target_frequency or ("HOURLY_6" if has_abnormal else "DAILY")

    output = MonitoringOutput(
        patient_id=patient_id,
        day=day,
        vitals_logged=vitals_data,
        abnormal_vitals_detected=has_abnormal,
        abnormal_readings=abnormal_flags,
        active_monitoring_frequency=active_freq,
        status="RECORDED",
    )
    return output.model_dump()
