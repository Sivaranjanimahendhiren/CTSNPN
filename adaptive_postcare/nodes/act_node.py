"""
Node 5: Act
Responsibility:
- Execute the selected tool/action determined in the Plan phase
- Record execution results in previous_actions
- Update current_action lifecycle
"""

from typing import Any, Dict, List
from ..state.patient_state import PatientState, CareAction
from ..tools.alert_tools import alert_care_team
from ..tools.care_tools import send_patient_notification, schedule_followup, log_intervention


def act_node(state: PatientState) -> Dict[str, Any]:
    """
    Step 5: Act
    Executes appropriate clinical tool for the planned action and logs execution.
    """
    action = state.get("next_action") or CareAction.CONTINUE.value
    patient_id = state.get("patient_id", "UNKNOWN")
    current_day = state.get("current_day", 0)
    previous_actions: List[Dict[str, Any]] = list(state.get("previous_actions", []))

    execution_result: Dict[str, Any] = {}

    if action == CareAction.ESCALATE.value:
        execution_result = alert_care_team.invoke({
            "patient_id": patient_id,
            "reason": f"Escalation triggered on Day {current_day}. Symptoms: {state.get('symptoms', [])}",
            "priority": "HIGH"
        })
    elif action == CareAction.REQUEST_MORE_DATA.value:
        execution_result = send_patient_notification.invoke({
            "patient_id": patient_id,
            "message": "We noticed incomplete check-in data. Please complete today's vitals and symptom check.",
            "channel": "IN_APP"
        })
    elif action == CareAction.MODIFY_CARE_PLAN.value:
        execution_result = log_intervention.invoke({
            "patient_id": patient_id,
            "intervention_type": "CARE_PLAN_MODIFIED",
            "details": {"day": current_day, "reason": "Adherence / symptom adjustment"}
        })
    elif action == CareAction.INCREASE_MONITORING.value:
        execution_result = schedule_followup.invoke({
            "patient_id": patient_id,
            "due_in_hours": 12,
            "purpose": "Increased monitoring cadence check"
        })
    elif action == CareAction.DECREASE_MONITORING.value:
        execution_result = schedule_followup.invoke({
            "patient_id": patient_id,
            "due_in_hours": 24,
            "purpose": "Standard step-down routine monitoring check"
        })
    elif action == CareAction.COMPLETE.value:
        execution_result = send_patient_notification.invoke({
            "patient_id": patient_id,
            "message": f"Congratulations! You have completed your post-discharge monitoring window of {state.get('care_duration_days')} days.",
            "channel": "SMS"
        })
    else:  # CONTINUE
        execution_result = log_intervention.invoke({
            "patient_id": patient_id,
            "intervention_type": "ROUTINE_MONITORING_CYCLE",
            "details": {"day": current_day}
        })

    action_record = {
        "action": action,
        "day": current_day,
        "result": execution_result,
        "status": "EXECUTED",
    }
    previous_actions.append(action_record)

    return {
        "current_action": action,
        "next_action": None,
        "previous_actions": previous_actions,
    }
