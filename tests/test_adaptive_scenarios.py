"""
Unit tests validating all eight clinical adaptive scenarios:
- SCENARIO 1: Patient is stable -> CONTINUE
- SCENARIO 2: Patient is improving consistently -> DECREASE_MONITORING
- SCENARIO 3: Patient condition is worsening -> INCREASE_MONITORING
- SCENARIO 4: Medication adherence decreases -> MODIFY_CARE_PLAN
- SCENARIO 5: Patient does not respond -> REQUEST_MORE_DATA (never assume healthy)
- SCENARIO 6: Patient gives inconsistent data -> lower data_quality & REQUEST_MORE_DATA
- SCENARIO 7: Configured escalation criteria satisfied -> ESCALATE
- SCENARIO 8: current_day >= care_duration_days -> COMPLETE
"""

import pytest
from adaptive_postcare.state.patient_state import (
    PatientStateModel,
    RiskLevel,
    PlanStatus,
    DataQuality,
    MonitoringFrequency,
    CareAction,
)
from adaptive_postcare.policies.adaptation_policies import (
    evaluate_adaptive_trajectory,
    AdaptationDecision,
)
from adaptive_postcare.nodes.observe_node import observe_node
from adaptive_postcare.nodes.understand_node import understand_node
from adaptive_postcare.nodes.risk_evaluation_node import risk_evaluation_node
from adaptive_postcare.nodes.plan_node import plan_node
from adaptive_postcare.nodes.act_node import act_node
from adaptive_postcare.nodes.feedback_node import feedback_node
from adaptive_postcare.nodes.adapt_node import adapt_node
from adaptive_postcare.edges.routing import route_after_adapt


def run_pipeline(state: dict) -> dict:
    """Helper to run the 7-node pipeline in sequence for a single cycle."""
    s = dict(state)
    s.update(observe_node(s))
    s.update(understand_node(s))
    s.update(risk_evaluation_node(s))
    s.update(plan_node(s))
    s.update(act_node(s))
    s.update(feedback_node(s))
    s.update(adapt_node(s))
    return s


# ==============================================================================
# SCENARIO 1: PATIENT IS STABLE
# ==============================================================================

def test_scenario_1_stable_patient():
    """Verify stable patient continues routine monitoring."""
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-SCENARIO-1",
        risk_score=0.20,
        risk_level=RiskLevel.LOW,
        care_duration_days=30,
    )
    state = model.to_state_dict()
    state["current_event"] = {
        "event_type": "daily_checkin",
        "day": 5,
        "feedback": {"symptoms": "none", "medication_taken": True, "energy_level": 8}
    }

    final_state = run_pipeline(state)
    decision = evaluate_adaptive_trajectory(final_state)

    assert decision.scenario_id == "SCENARIO_1_STABLE"
    assert decision.selected_action == CareAction.CONTINUE.value
    assert final_state["current_action"] == CareAction.CONTINUE.value
    assert route_after_adapt(final_state) == "continue"


# ==============================================================================
# SCENARIO 2: PATIENT IS IMPROVING CONSISTENTLY
# ==============================================================================

def test_scenario_2_improving_patient():
    """Verify consistently improving patient on elevated monitoring steps down cadence."""
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-SCENARIO-2",
        risk_score=0.55,
        risk_level=RiskLevel.MEDIUM,
        care_duration_days=30,
    )
    state = model.to_state_dict()
    state["monitoring_frequency"] = MonitoringFrequency.HOURLY_12.value
    state["symptoms"] = []
    state["medication_adherence"] = 1.0
    state["current_event"] = {
        "event_type": "daily_checkin",
        "day": 10,
        "feedback": {"symptoms": "none", "medication_taken": True}
    }

    decision = evaluate_adaptive_trajectory(state)
    assert decision.scenario_id == "SCENARIO_2_IMPROVING"
    assert decision.selected_action == CareAction.DECREASE_MONITORING.value

    final_state = run_pipeline(state)
    assert final_state["current_action"] == CareAction.DECREASE_MONITORING.value
    assert final_state["monitoring_frequency"] == MonitoringFrequency.TWICE_DAILY.value
    assert route_after_adapt(final_state) == "decrease_monitoring"


# ==============================================================================
# SCENARIO 3: PATIENT CONDITION IS WORSENING
# ==============================================================================

def test_scenario_3_worsening_patient():
    """Verify worsening symptoms trigger increased monitoring."""
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-SCENARIO-3",
        risk_score=0.40,
        risk_level=RiskLevel.MEDIUM,
        care_duration_days=30,
    )
    state = model.to_state_dict()
    state["monitoring_frequency"] = MonitoringFrequency.DAILY.value
    state["current_event"] = {
        "event_type": "symptom_report",
        "day": 6,
        "feedback": {"symptoms": ["mild persistent cough", "fatigue"], "medication_taken": True}
    }

    final_state = run_pipeline(state)
    decision = evaluate_adaptive_trajectory(final_state)

    assert decision.scenario_id == "SCENARIO_3_WORSENING"
    assert decision.selected_action == CareAction.INCREASE_MONITORING.value
    assert final_state["monitoring_frequency"] == MonitoringFrequency.TWICE_DAILY.value
    assert route_after_adapt(final_state) == "increase_monitoring"


# ==============================================================================
# SCENARIO 4: MEDICATION ADHERENCE DECREASES
# ==============================================================================

def test_scenario_4_adherence_decrease():
    """Verify drop in medication adherence triggers care plan modification."""
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-SCENARIO-4",
        risk_score=0.35,
        risk_level=RiskLevel.MEDIUM,
        care_duration_days=30,
    )
    state = model.to_state_dict()
    state["current_event"] = {
        "event_type": "medication_log",
        "day": 4,
        "feedback": {"symptoms": "none", "medication_taken": False}
    }

    final_state = run_pipeline(state)
    decision = evaluate_adaptive_trajectory(final_state)

    assert decision.scenario_id == "SCENARIO_4_ADHERENCE_DECREASE"
    assert decision.selected_action == CareAction.MODIFY_CARE_PLAN.value
    assert final_state["care_plan"]["adherence_support_active"] is True
    assert route_after_adapt(final_state) == "modify_care_plan"


# ==============================================================================
# SCENARIO 5: PATIENT DOES NOT RESPOND (NO CHECK-IN)
# ==============================================================================

def test_scenario_5_patient_does_not_respond():
    """Verify missing response requests more data without assuming the patient is healthy."""
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-SCENARIO-5",
        risk_score=0.45,
        risk_level=RiskLevel.MEDIUM,
        care_duration_days=30,
    )
    state = model.to_state_dict()
    # No event / no feedback provided
    state["current_event"] = None

    final_state = run_pipeline(state)
    decision = evaluate_adaptive_trajectory(final_state)

    assert decision.scenario_id == "SCENARIO_5_NO_RESPONSE"
    assert decision.selected_action == CareAction.REQUEST_MORE_DATA.value
    assert final_state["data_quality"] == DataQuality.INCOMPLETE.value
    assert route_after_adapt(final_state) == "request_more_data"


# ==============================================================================
# SCENARIO 6: PATIENT GIVES INCONSISTENT / PARTIAL DATA
# ==============================================================================

def test_scenario_6_inconsistent_data():
    """Verify partial or degraded data lowers quality score and requests clarification."""
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-SCENARIO-6",
        risk_score=0.40,
        risk_level=RiskLevel.MEDIUM,
        care_duration_days=25,
    )
    state = model.to_state_dict()
    # Empty feedback dict
    state["current_event"] = {
        "event_type": "daily_checkin",
        "day": 3,
        "feedback": {}
    }

    final_state = run_pipeline(state)
    decision = evaluate_adaptive_trajectory(final_state)

    assert final_state["data_quality"] == DataQuality.POOR.value
    assert decision.selected_action == CareAction.REQUEST_MORE_DATA.value
    assert route_after_adapt(final_state) == "request_more_data"


# ==============================================================================
# SCENARIO 7: ESCALATION CRITERIA SATISFIED
# ==============================================================================

def test_scenario_7_escalation_criteria_satisfied():
    """Verify emergency red-flag symptoms trigger immediate ESCALATE action."""
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-SCENARIO-7",
        risk_score=0.80,
        risk_level=RiskLevel.HIGH,
        care_duration_days=30,
    )
    state = model.to_state_dict()
    state["current_event"] = {
        "event_type": "symptom_report",
        "day": 8,
        "feedback": {"symptoms": ["chest pain", "shortness of breath"], "medication_taken": True}
    }

    final_state = run_pipeline(state)
    decision = evaluate_adaptive_trajectory(final_state)

    assert decision.scenario_id == "SCENARIO_7_ESCALATION"
    assert decision.selected_action == CareAction.ESCALATE.value
    assert final_state["escalation_required"] is True
    assert final_state["plan_status"] == PlanStatus.ESCALATED.value
    assert route_after_adapt(final_state) == "escalate"


# ==============================================================================
# SCENARIO 8: CARE DURATION REACHED (current_day >= care_duration_days)
# ==============================================================================

def test_scenario_8_care_duration_completed():
    """Verify reaching designated care_duration_days completes monitoring lifecycle."""
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-SCENARIO-8",
        risk_score=0.25,
        risk_level=RiskLevel.LOW,
        care_duration_days=14,  # Variable 14-day duration
    )
    state = model.to_state_dict()
    state["current_event"] = {
        "event_type": "daily_checkin",
        "day": 14,  # Exactly care_duration_days
        "feedback": {"symptoms": "none", "medication_taken": True}
    }

    final_state = run_pipeline(state)
    decision = evaluate_adaptive_trajectory(final_state)

    assert decision.scenario_id == "SCENARIO_8_COMPLETE"
    assert decision.selected_action == CareAction.COMPLETE.value
    assert final_state["plan_status"] == PlanStatus.COMPLETED.value
    assert route_after_adapt(final_state) == "complete"
