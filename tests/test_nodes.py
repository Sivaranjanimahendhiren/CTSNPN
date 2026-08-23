"""
Unit tests for the seven core LangGraph nodes:
1. Observe
2. Understand
3. Risk Evaluation
4. Plan
5. Act
6. Feedback
7. Adapt
"""

import pytest
from adaptive_postcare.state.patient_state import (
    PatientState,
    PatientStateModel,
    RiskLevel,
    PlanStatus,
    DataQuality,
    MonitoringFrequency,
    CareAction,
)
from adaptive_postcare.nodes.observe_node import observe_node
from adaptive_postcare.nodes.understand_node import understand_node
from adaptive_postcare.nodes.risk_evaluation_node import risk_evaluation_node
from adaptive_postcare.nodes.plan_node import plan_node
from adaptive_postcare.nodes.act_node import act_node
from adaptive_postcare.nodes.feedback_node import feedback_node
from adaptive_postcare.nodes.adapt_node import adapt_node


@pytest.fixture
def base_state() -> PatientState:
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-TEST-01",
        risk_score=0.45,
        risk_level=RiskLevel.MEDIUM,
        care_duration_days=30,
    )
    return model.to_state_dict()


# ==============================================================================
# 1. OBSERVE NODE TESTS
# ==============================================================================

def test_observe_node_with_valid_event(base_state):
    state = dict(base_state)
    state["current_event"] = {
        "event_type": "daily_checkin",
        "day": 3,
        "feedback": {"symptoms": "improving", "medication_taken": True}
    }
    diff = observe_node(state)
    assert diff["current_day"] == 3
    assert diff["last_checkin_day"] == 3
    assert diff["data_quality"] == DataQuality.GOOD.value


def test_observe_node_with_incomplete_event(base_state):
    state = dict(base_state)
    state["current_event"] = {
        "event_type": "daily_checkin",
        "day": 2,
        "feedback": {}
    }
    diff = observe_node(state)
    assert diff["data_quality"] == DataQuality.POOR.value


def test_observe_node_without_event(base_state):
    state = dict(base_state)
    state["current_event"] = None
    diff = observe_node(state)
    assert diff["data_quality"] == DataQuality.INCOMPLETE.value


# ==============================================================================
# 2. UNDERSTAND NODE TESTS
# ==============================================================================

def test_understand_node_extracts_symptoms_and_adherence(base_state):
    state = dict(base_state)
    state["symptoms"] = ["mild fatigue"]
    state["medication_adherence"] = 1.0
    state["current_event"] = {
        "feedback": {
            "symptoms": ["headache"],
            "medication_taken": False
        }
    }
    diff = understand_node(state)
    assert "headache" in diff["symptoms"]
    assert "mild fatigue" in diff["symptoms"]
    assert diff["medication_adherence"] < 1.0


def test_understand_node_adherence_maintained_when_taken(base_state):
    state = dict(base_state)
    state["medication_adherence"] = 1.0
    state["current_event"] = {
        "feedback": {
            "symptoms": "none",
            "medication_taken": True
        }
    }
    diff = understand_node(state)
    assert diff["medication_adherence"] == 1.0


# ==============================================================================
# 3. RISK EVALUATION NODE TESTS
# ==============================================================================

def test_risk_eval_red_flag_symptoms_triggers_escalation(base_state):
    state = dict(base_state)
    state["symptoms"] = ["chest pain", "dizziness"]
    diff = risk_evaluation_node(state)
    assert diff["escalation_required"] is True


def test_risk_eval_critical_baseline_triggers_escalation(base_state):
    state = dict(base_state)
    state["risk_level"] = RiskLevel.CRITICAL.value
    diff = risk_evaluation_node(state)
    assert diff["escalation_required"] is True


def test_risk_eval_stable_patient_no_escalation(base_state):
    state = dict(base_state)
    state["risk_level"] = RiskLevel.LOW.value
    state["symptoms"] = []
    state["medication_adherence"] = 1.0
    diff = risk_evaluation_node(state)
    assert diff["escalation_required"] is False


# ==============================================================================
# 4. PLAN NODE TESTS
# ==============================================================================

def test_plan_node_escalate(base_state):
    state = dict(base_state)
    state["escalation_required"] = True
    diff = plan_node(state)
    assert diff["next_action"] == CareAction.ESCALATE.value
    assert diff["plan_status"] == PlanStatus.ESCALATED.value


def test_plan_node_complete_when_duration_reached(base_state):
    state = dict(base_state)
    state["current_day"] = 30
    state["care_duration_days"] = 30
    state["escalation_required"] = False
    diff = plan_node(state)
    assert diff["next_action"] == CareAction.COMPLETE.value
    assert diff["plan_status"] == PlanStatus.COMPLETED.value


def test_plan_node_request_more_data(base_state):
    state = dict(base_state)
    state["data_quality"] = DataQuality.POOR.value
    diff = plan_node(state)
    assert diff["next_action"] == CareAction.REQUEST_MORE_DATA.value


def test_plan_node_modify_care_plan_low_adherence(base_state):
    state = dict(base_state)
    state["medication_adherence"] = 0.6
    diff = plan_node(state)
    assert diff["next_action"] == CareAction.MODIFY_CARE_PLAN.value


def test_plan_node_increase_monitoring_on_symptoms(base_state):
    state = dict(base_state)
    state["symptoms"] = ["mild cough"]
    state["monitoring_frequency"] = "DAILY"
    diff = plan_node(state)
    assert diff["next_action"] == CareAction.INCREASE_MONITORING.value


def test_plan_node_continue_routine(base_state):
    state = dict(base_state)
    state["symptoms"] = []
    state["medication_adherence"] = 1.0
    state["data_quality"] = DataQuality.GOOD.value
    diff = plan_node(state)
    assert diff["next_action"] == CareAction.CONTINUE.value


# ==============================================================================
# 5. ACT NODE TESTS
# ==============================================================================

def test_act_node_executes_escalation(base_state):
    state = dict(base_state)
    state["next_action"] = CareAction.ESCALATE.value
    diff = act_node(state)
    assert diff["current_action"] == CareAction.ESCALATE.value
    assert diff["next_action"] is None
    assert len(diff["previous_actions"]) == 1
    assert diff["previous_actions"][0]["action"] == CareAction.ESCALATE.value


def test_act_node_executes_continue(base_state):
    state = dict(base_state)
    state["next_action"] = CareAction.CONTINUE.value
    diff = act_node(state)
    assert diff["current_action"] == CareAction.CONTINUE.value
    assert len(diff["previous_actions"]) == 1


# ==============================================================================
# 6. FEEDBACK NODE TESTS
# ==============================================================================

def test_feedback_node_records_history(base_state):
    state = dict(base_state)
    state["current_day"] = 4
    state["current_action"] = CareAction.CONTINUE.value
    state["current_event"] = {
        "event_type": "daily_checkin",
        "feedback": {"symptoms": "feeling well", "energy_level": 8}
    }
    diff = feedback_node(state)
    assert len(diff["feedback_history"]) == 1
    assert diff["feedback_history"][0]["day"] == 4
    assert diff["latest_feedback"]["energy_level"] == 8


# ==============================================================================
# 7. ADAPT NODE TESTS
# ==============================================================================

def test_adapt_node_steps_up_monitoring_frequency(base_state):
    state = dict(base_state)
    state["current_action"] = CareAction.INCREASE_MONITORING.value
    state["monitoring_frequency"] = MonitoringFrequency.DAILY.value
    diff = adapt_node(state)
    assert diff["monitoring_frequency"] == MonitoringFrequency.TWICE_DAILY.value
    assert len(diff["adaptation_notes"]) > 0


def test_adapt_node_completes_care_strategy(base_state):
    state = dict(base_state)
    state["current_day"] = 30
    state["care_duration_days"] = 30
    diff = adapt_node(state)
    assert diff["plan_status"] == PlanStatus.COMPLETED.value
