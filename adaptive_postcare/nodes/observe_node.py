"""
Node 1: Observe
Responsibility:
- Read current PatientState
- Read current event payload
- Determine available information, validate completeness, and assess data quality
"""

from typing import Any, Dict
from ..state.patient_state import PatientState, DataQuality


def observe_node(state: PatientState) -> Dict[str, Any]:
    """
    Step 1: Observe
    Inspects incoming patient telemetry or event, advances day counters,
    and determines data availability and quality.
    """
    event = state.get("current_event") or {}
    feedback = event.get("feedback", {})
    event_day = event.get("day")

    current_day = state.get("current_day", 0)
    care_duration = state.get("care_duration_days", 30)

    # Advance current_day if valid event_day provided, bounded by care_duration_days
    if event_day is not None and isinstance(event_day, int):
        current_day = min(max(current_day, event_day), care_duration)

    last_checkin_day = state.get("last_checkin_day")
    if event_day is not None:
        last_checkin_day = current_day

    # Determine information availability / data quality
    if not event:
        data_quality = DataQuality.INCOMPLETE.value
    elif not feedback or (isinstance(feedback, dict) and not feedback):
        data_quality = DataQuality.POOR.value
    elif isinstance(feedback, dict):
        has_symptoms = "symptoms" in feedback and feedback["symptoms"] is not None
        has_meds = "medication_taken" in feedback and feedback["medication_taken"] is not None
        if has_symptoms and has_meds:
            data_quality = DataQuality.GOOD.value
        elif has_symptoms or has_meds:
            data_quality = DataQuality.DEGRADED.value
        else:
            data_quality = DataQuality.POOR.value
    else:
        data_quality = DataQuality.GOOD.value

    return {
        "current_day": current_day,
        "last_checkin_day": last_checkin_day,
        "data_quality": data_quality,
    }
