"""
Node 6: Feedback
Responsibility:
- Process the result of the action or patient response
- Append structured entry to feedback_history
- Record latest feedback state
"""

from typing import Any, Dict, List
from ..state.patient_state import PatientState


def feedback_node(state: PatientState) -> Dict[str, Any]:
    """
    Step 6: Feedback
    Ingests outcome of the executed action and appends patient feedback to history.
    """
    event = state.get("current_event") or {}
    feedback_data = event.get("feedback")
    current_day = state.get("current_day", 0)
    feedback_history: List[Dict[str, Any]] = list(state.get("feedback_history", []))

    if feedback_data:
        entry = {
            "day": current_day,
            "event_type": event.get("event_type", "daily_checkin"),
            "feedback": feedback_data,
            "action_executed": state.get("current_action"),
        }
        feedback_history.append(entry)

    return {
        "feedback_history": feedback_history,
        "latest_feedback": feedback_data if feedback_data else state.get("latest_feedback"),
    }
