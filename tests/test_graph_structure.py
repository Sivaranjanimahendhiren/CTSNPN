"""
Comprehensive graph tests verifying StateGraph assembly, execution, and conditional routing after Adapt:
1. Stable Patient (CONTINUE)
2. Improving Patient (DECREASE_MONITORING)
3. Worsening Patient (INCREASE_MONITORING)
4. Missing Data (REQUEST_MORE_DATA)
5. Inconsistent Data (DEGRADED quality)
6. Escalation (ESCALATE -> Escalate Node -> END)
7. Completed Care Plan (COMPLETE -> END)
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
from adaptive_postcare.graph import build_postcare_graph, get_compiled_graph
from adaptive_postcare.edges.routing import route_after_adapt
from adaptive_postcare.nodes.observe_node import observe_node
from adaptive_postcare.nodes.understand_node import understand_node
from adaptive_postcare.nodes.risk_evaluation_node import risk_evaluation_node
from adaptive_postcare.nodes.plan_node import plan_node
from adaptive_postcare.nodes.act_node import act_node
from adaptive_postcare.nodes.feedback_node import feedback_node
from adaptive_postcare.nodes.adapt_node import adapt_node


def run_pipeline_step(state: dict) -> dict:
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


def test_graph_structure_and_nodes_registered():
    """Verify graph builder registers all 8 nodes (7 core + 1 escalate)."""
    graph_builder = build_postcare_graph()
    assert graph_builder is not None
    expected_nodes = {"observe", "understand", "risk_evaluation", "plan", "act", "feedback", "adapt", "escalate"}
    assert expected_nodes.issubset(set(graph_builder.nodes.keys()))


# ==============================================================================
# ROUTE 1: STABLE PATIENT -> CONTINUE
# ==============================================================================

def test_route_stable_patient():
    """Test stable patient with perfect adherence and no symptoms routes to CONTINUE."""
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-STABLE",
        risk_score=0.2,
        risk_level=RiskLevel.LOW,
        care_duration_days=30,
    )
    state = model.to_state_dict()
    state["current_event"] = {
        "event_type": "daily_checkin",
        "day": 5,
        "feedback": {"symptoms": "none", "medication_taken": True, "energy_level": 9}
    }

    final_state = run_pipeline_step(state)
    assert final_state["current_action"] == CareAction.CONTINUE.value
    assert final_state["escalation_required"] is False

    next_route = route_after_adapt(final_state)
    assert next_route == "continue"


# ==============================================================================
# ROUTE 2: IMPROVING PATIENT -> DECREASE_MONITORING
# ==============================================================================

def test_route_improving_patient():
    """Test patient with resolved symptoms on intense monitoring steps down frequency."""
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-IMPROVING",
        risk_score=0.5,
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
        "feedback": {"symptoms": "none", "medication_taken": True, "energy_level": 8}
    }

    final_state = run_pipeline_step(state)
    assert final_state["current_action"] == CareAction.DECREASE_MONITORING.value
    assert final_state["monitoring_frequency"] == MonitoringFrequency.TWICE_DAILY.value

    next_route = route_after_adapt(final_state)
    assert next_route == "decrease_monitoring"


# ==============================================================================
# ROUTE 3: WORSENING PATIENT -> INCREASE_MONITORING
# ==============================================================================

def test_route_worsening_patient():
    """Test patient reporting new non-emergency symptoms steps up monitoring frequency."""
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-WORSENING",
        risk_score=0.4,
        risk_level=RiskLevel.MEDIUM,
        care_duration_days=30,
    )
    state = model.to_state_dict()
    state["monitoring_frequency"] = MonitoringFrequency.DAILY.value
    state["current_event"] = {
        "event_type": "symptom_report",
        "day": 7,
        "feedback": {"symptoms": ["mild persistent cough", "fatigue"], "medication_taken": True}
    }

    final_state = run_pipeline_step(state)
    assert final_state["current_action"] == CareAction.INCREASE_MONITORING.value
    assert final_state["monitoring_frequency"] == MonitoringFrequency.TWICE_DAILY.value

    next_route = route_after_adapt(final_state)
    assert next_route == "increase_monitoring"


# ==============================================================================
# ROUTE 4: MISSING DATA -> REQUEST_MORE_DATA
# ==============================================================================

def test_route_missing_data():
    """Test check-in with completely empty feedback triggers REQUEST_MORE_DATA."""
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-NODATA",
        risk_score=0.3,
        risk_level=RiskLevel.LOW,
        care_duration_days=30,
    )
    state = model.to_state_dict()
    state["current_event"] = {
        "event_type": "daily_checkin",
        "day": 4,
        "feedback": {}
    }

    final_state = run_pipeline_step(state)
    assert final_state["data_quality"] == DataQuality.POOR.value
    assert final_state["current_action"] == CareAction.REQUEST_MORE_DATA.value

    next_route = route_after_adapt(final_state)
    assert next_route == "request_more_data"


# ==============================================================================
# ROUTE 5: INCONSISTENT DATA -> DEGRADED DATA QUALITY
# ==============================================================================

def test_route_inconsistent_data():
    """Test partial feedback (missing medication data) evaluates data quality as DEGRADED."""
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-INCONSISTENT",
        risk_score=0.35,
        risk_level=RiskLevel.MEDIUM,
        care_duration_days=20,
    )
    state = model.to_state_dict()
    # Symptoms provided, but medication adherence field omitted
    state["current_event"] = {
        "event_type": "daily_checkin",
        "day": 6,
        "feedback": {"symptoms": "mild nausea"}
    }

    final_state = run_pipeline_step(state)
    assert final_state["data_quality"] == DataQuality.DEGRADED.value
    assert "mild nausea" in final_state["symptoms"]


# ==============================================================================
# ROUTE 6: ESCALATION -> ESCALATE TOOL -> END
# ==============================================================================

def test_route_escalation_acute_symptoms():
    """Test emergency red-flag symptoms route directly to ESCALATE."""
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-EMERGENCY",
        risk_score=0.75,
        risk_level=RiskLevel.HIGH,
        care_duration_days=30,
    )
    state = model.to_state_dict()
    state["current_event"] = {
        "event_type": "symptom_report",
        "day": 8,
        "feedback": {"symptoms": ["chest pain", "severe shortness of breath"], "medication_taken": True}
    }

    final_state = run_pipeline_step(state)
    assert final_state["escalation_required"] is True
    assert final_state["current_action"] == CareAction.ESCALATE.value
    assert final_state["plan_status"] == PlanStatus.ESCALATED.value

    next_route = route_after_adapt(final_state)
    assert next_route == "escalate"

    # Verify compiled graph execution reaches terminal escalation
    compiled_graph = get_compiled_graph()
    output_state = compiled_graph.invoke(state, config={"recursion_limit": 15})
    assert output_state["plan_status"] == PlanStatus.ESCALATED.value


# ==============================================================================
# ROUTE 7: COMPLETED CARE PLAN -> END
# ==============================================================================

def test_route_completed_care_plan():
    """Test reaching care_duration_days completes the care window and routes to complete (END)."""
    model = PatientStateModel.initialize_from_external_model(
        patient_id="PT-COMPLETED",
        risk_score=0.25,
        risk_level=RiskLevel.LOW,
        care_duration_days=21,
    )
    state = model.to_state_dict()
    state["current_event"] = {
        "event_type": "daily_checkin",
        "day": 21,  # Day equals care_duration_days
        "feedback": {"symptoms": "none", "medication_taken": True}
    }

    final_state = run_pipeline_step(state)
    assert final_state["current_action"] == CareAction.COMPLETE.value
    assert final_state["plan_status"] == PlanStatus.COMPLETED.value

    next_route = route_after_adapt(final_state)
    assert next_route == "complete"

    # Verify compiled graph execution finishes at END
    compiled_graph = get_compiled_graph()
    output_state = compiled_graph.invoke(state, config={"recursion_limit": 15})
    assert output_state["plan_status"] == PlanStatus.COMPLETED.value
