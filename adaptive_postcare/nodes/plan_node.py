"""
Node 4: Plan
Responsibility:
- Select the next valid action using explicit configurable adaptation policies
- Possible actions:
  - CONTINUE
  - INCREASE_MONITORING
  - DECREASE_MONITORING
  - REQUEST_MORE_DATA
  - MODIFY_CARE_PLAN
  - ESCALATE
  - COMPLETE
"""

from typing import Any, Dict
from ..state.patient_state import PatientState
from ..policies.adaptation_policies import evaluate_adaptive_trajectory


def plan_node(state: PatientState) -> Dict[str, Any]:
    """
    Step 4: Plan
    Evaluates patient trajectory across the 8 clinical scenarios and sets the next operational action.
    """
    decision = evaluate_adaptive_trajectory(state)
    care_plan = dict(state.get("care_plan", {}))

    if decision.selected_action == "MODIFY_CARE_PLAN":
        care_plan["adherence_support_active"] = True

    return {
        "next_action": decision.selected_action,
        "plan_status": decision.plan_status,
        "care_plan": care_plan,
    }
