"""
Node 7: Adapt
Responsibility:
- Compare previous state against current state across the 8 clinical scenarios
- Leverage LLM for qualitative reasoning (observed barriers, non-clinical focus)
- Update monitoring cadence, care plan parameters, and lifecycle status
- LangGraph routes workflow based on the updated state
"""

from typing import Any, Dict, List
from ..state.patient_state import PatientState, MonitoringFrequency, CareAction
from ..policies.adaptation_policies import evaluate_adaptive_trajectory
from ..llm.service import LLMService
from ..llm.schemas import AdaptationReasoning


def adapt_node(state: PatientState) -> Dict[str, Any]:
    """
    Step 7: Adapt
    Synthesizes the completed cycle, performs controlled LLM qualitative reasoning,
    and updates monitoring frequency, plan status, and adaptation notes.
    """
    current_day = state.get("current_day", 0)
    current_action = state.get("current_action")
    current_freq = state.get("monitoring_frequency", MonitoringFrequency.DAILY.value)
    care_plan = dict(state.get("care_plan", {}))
    adaptation_notes: List[str] = list(state.get("adaptation_notes", []))
    patient_id = state.get("patient_id", "UNKNOWN")
    risk_level = state.get("risk_level", "LOW")
    care_duration = state.get("care_duration_days", 30)
    symptoms = state.get("symptoms", [])
    adherence = state.get("medication_adherence", 1.0)
    latest_feedback = state.get("latest_feedback")

    # 1. Deterministic trajectory evaluation across 8 scenarios
    decision = evaluate_adaptive_trajectory(state)

    # 2. Controlled LLM qualitative reasoning for qualitative summary and barrier detection
    llm_service = LLMService()
    reasoning: AdaptationReasoning = llm_service.assess_adaptation(
        patient_id=patient_id,
        risk_level=risk_level,
        current_day=current_day,
        care_duration_days=care_duration,
        symptoms=symptoms,
        medication_adherence=adherence,
        latest_feedback=latest_feedback,
    )

    # 3. Determine updated monitoring frequency
    updated_freq = decision.target_frequency or current_freq
    if current_action == CareAction.INCREASE_MONITORING.value:
        step_up_map = {
            MonitoringFrequency.WEEKLY.value: MonitoringFrequency.DAILY.value,
            MonitoringFrequency.DAILY.value: MonitoringFrequency.TWICE_DAILY.value,
            MonitoringFrequency.TWICE_DAILY.value: MonitoringFrequency.HOURLY_12.value,
            MonitoringFrequency.HOURLY_12.value: MonitoringFrequency.HOURLY_6.value,
            MonitoringFrequency.HOURLY_6.value: MonitoringFrequency.HOURLY_6.value,
        }
        updated_freq = step_up_map.get(current_freq, MonitoringFrequency.TWICE_DAILY.value)
    elif current_action == CareAction.DECREASE_MONITORING.value:
        step_down_map = {
            MonitoringFrequency.HOURLY_6.value: MonitoringFrequency.HOURLY_12.value,
            MonitoringFrequency.HOURLY_12.value: MonitoringFrequency.TWICE_DAILY.value,
            MonitoringFrequency.TWICE_DAILY.value: MonitoringFrequency.DAILY.value,
        }
        updated_freq = step_down_map.get(current_freq, MonitoringFrequency.DAILY.value)
    elif current_action == CareAction.ESCALATE.value:
        updated_freq = MonitoringFrequency.HOURLY_6.value

    # 4. Apply notes and adaptations
    adaptation_notes.append(f"Day {current_day} [{decision.scenario_id}]: {decision.reason}")

    if reasoning.observed_barriers:
        adaptation_notes.append(f"Observed barrier(s): {', '.join(reasoning.observed_barriers)}")

    if decision.selected_action == "MODIFY_CARE_PLAN" or current_action == CareAction.MODIFY_CARE_PLAN.value:
        care_plan["last_adapted_day"] = current_day

    return {
        "monitoring_frequency": updated_freq,
        "plan_status": decision.plan_status,
        "care_plan": care_plan,
        "adaptation_notes": adaptation_notes,
    }
