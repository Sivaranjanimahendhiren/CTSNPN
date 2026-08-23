"""
Conditional routing functions for the Adaptive Post-Care StateGraph.
Uses PatientState attributes to deterministically route state transitions after the Adapt node.
"""

from typing import Literal
from ..state.patient_state import PatientState, CareAction, PlanStatus


def route_after_adapt(
    state: PatientState,
) -> Literal[
    "continue",
    "increase_monitoring",
    "decrease_monitoring",
    "request_more_data",
    "modify_care_plan",
    "escalate",
    "complete",
]:
    """
    Evaluates PatientState after the Adapt node to determine the next graph transition.

    Routing Table:
    1. CONTINUE            -> "continue"            -> Observe
    2. INCREASE_MONITORING -> "increase_monitoring" -> Observe
    3. DECREASE_MONITORING -> "decrease_monitoring" -> Observe
    4. REQUEST_MORE_DATA   -> "request_more_data"   -> Feedback
    5. MODIFY_CARE_PLAN    -> "modify_care_plan"    -> Plan
    6. ESCALATE            -> "escalate"            -> Escalate Tool/Node
    7. COMPLETE            -> "complete"            -> END
    """
    plan_status = state.get("plan_status")
    current_action = state.get("current_action")
    escalation_required = state.get("escalation_required", False)
    current_day = state.get("current_day", 0)
    care_duration = state.get("care_duration_days", 30)

    # 1. Check for Completion
    if plan_status == PlanStatus.COMPLETED.value or (current_day >= care_duration and not escalation_required):
        return "complete"

    # 2. Check for Escalation
    if escalation_required or current_action == CareAction.ESCALATE.value or plan_status == PlanStatus.ESCALATED.value:
        return "escalate"

    # 3. Check for Request More Data
    if current_action == CareAction.REQUEST_MORE_DATA.value:
        return "request_more_data"

    # 4. Check for Modify Care Plan
    if current_action == CareAction.MODIFY_CARE_PLAN.value:
        return "modify_care_plan"

    # 5. Check for Increase Monitoring
    if current_action == CareAction.INCREASE_MONITORING.value:
        return "increase_monitoring"

    # 6. Check for Decrease Monitoring
    if current_action == CareAction.DECREASE_MONITORING.value:
        return "decrease_monitoring"

    # 7. Default: Continue
    return "continue"
