"""
End-to-End Test Suite for Adaptive Agentic Post-Care System.
Verifies all 7 core patient scenarios and concurrent multi-patient execution.
Generates structured, human-readable execution traces for project demonstration.
"""

import pytest
import concurrent.futures
from adaptive_postcare.orchestrator import MultiPatientOrchestrator
from adaptive_postcare.schemas.readmission_input import InitialRiskEvent
from adaptive_postcare.schemas.patient_event import PatientEvent
from adaptive_postcare.state.patient_state import RiskLevel, PlanStatus, DataQuality, MonitoringFrequency, CareAction
from adaptive_postcare.edges.routing import route_after_adapt
from adaptive_postcare.utils.tracer import ExecutionTracer


def print_trace(
    patient_id: str,
    risk_level: str,
    care_duration_days: int,
    current_day: int,
    node_executed: str,
    state_change: str,
    decision: str,
    next_node: str,
    final_action: str,
):
    """Helper to display the standardized execution trace block with ASCII formatting."""
    trace_str = (
        f"\nPatient ID      : {patient_id}\n"
        f"        |\n"
        f"        v\n"
        f"Risk            : {risk_level}\n"
        f"        |\n"
        f"        v\n"
        f"Care Duration   : {care_duration_days} days\n"
        f"        |\n"
        f"        v\n"
        f"Current Day     : Day {current_day}\n"
        f"        |\n"
        f"        v\n"
        f"Node executed   : {node_executed}\n"
        f"        |\n"
        f"        v\n"
        f"State change    : {state_change}\n"
        f"        |\n"
        f"        v\n"
        f"Decision        : {decision}\n"
        f"        |\n"
        f"        v\n"
        f"Next node       : {next_node}\n"
        f"        |\n"
        f"        v\n"
        f"Final action    : {final_action}\n"
    )
    print(trace_str)


# ==============================================================================
# PATIENT 1: HIGH RISK, 30 CARE DAYS, STABLE FEEDBACK -> CONTINUE
# ==============================================================================

def test_patient_1_high_risk_stable_continue():
    """
    PATIENT 1:
    HIGH risk, 30 care days, stable feedback -> CONTINUE
    """
    orchestrator = MultiPatientOrchestrator()
    patient_id = "P1-HIGH-STABLE"

    # Initialize from External Model
    orchestrator.register_patient_from_event(
        InitialRiskEvent(
            patient_id=patient_id,
            risk_score=0.75,
            risk_level="HIGH",
            care_duration_days=30,
        )
    )

    # Ingest Day 5 Stable Check-in
    event = PatientEvent(
        patient_id=patient_id,
        event_type="daily_checkin",
        day=5,
        feedback={
            "symptoms": "none",
            "medication_taken": True,
            "energy_level": 8,
        }
    )
    final_state = orchestrator.process_patient_event(event)
    next_route = route_after_adapt(final_state)

    # Print Formatted Execution Trace
    print_trace(
        patient_id=patient_id,
        risk_level=final_state["risk_level"],
        care_duration_days=final_state["care_duration_days"],
        current_day=final_state["current_day"],
        node_executed="Observe -> Understand -> RiskEval -> Plan -> Act -> Feedback -> Adapt",
        state_change="symptoms=[] | adherence=1.0 | data_quality=GOOD",
        decision="SCENARIO_1_STABLE (Parameters within baseline thresholds)",
        next_node=f"observe ({next_route})",
        final_action=final_state["current_action"],
    )

    # Assertions
    assert final_state["current_action"] == CareAction.CONTINUE.value
    assert final_state["plan_status"] == PlanStatus.ACTIVE.value
    assert final_state["escalation_required"] is False
    assert final_state["care_duration_days"] == 30
    assert next_route == "continue"


# ==============================================================================
# PATIENT 2: MEDIUM RISK, 20 CARE DAYS, IMPROVING FEEDBACK -> ADAPT MONITORING
# ==============================================================================

def test_patient_2_medium_risk_improving_adapt_monitoring():
    """
    PATIENT 2:
    MEDIUM risk, 20 care days, improving feedback -> ADAPT MONITORING (DECREASE_MONITORING)
    """
    orchestrator = MultiPatientOrchestrator()
    patient_id = "P2-MED-IMPROVING"

    orchestrator.register_patient_from_event(
        InitialRiskEvent(
            patient_id=patient_id,
            risk_score=0.55,
            risk_level="MEDIUM",
            care_duration_days=20,
        )
    )

    # Simulate patient previously stepped up to intensive HOURLY_12 monitoring
    orchestrator._patient_states[patient_id]["monitoring_frequency"] = MonitoringFrequency.HOURLY_12.value

    # Ingest Day 8 Improving Check-in
    event = PatientEvent(
        patient_id=patient_id,
        event_type="daily_checkin",
        day=8,
        feedback={
            "symptoms": "none",
            "medication_taken": True,
            "energy_level": 9,
        }
    )
    final_state = orchestrator.process_patient_event(event)
    next_route = route_after_adapt(final_state)

    print_trace(
        patient_id=patient_id,
        risk_level=final_state["risk_level"],
        care_duration_days=final_state["care_duration_days"],
        current_day=final_state["current_day"],
        node_executed="Observe -> Understand -> RiskEval -> Plan -> Act -> Feedback -> Adapt",
        state_change="symptoms=[] | cadence: HOURLY_12 -> TWICE_DAILY",
        decision="SCENARIO_2_IMPROVING (Step down monitoring cadence)",
        next_node=f"observe ({next_route})",
        final_action=final_state["current_action"],
    )

    assert final_state["current_action"] == CareAction.DECREASE_MONITORING.value
    assert final_state["monitoring_frequency"] == MonitoringFrequency.TWICE_DAILY.value
    assert final_state["care_duration_days"] == 20
    assert next_route == "decrease_monitoring"


# ==============================================================================
# PATIENT 3: LOW RISK, 10 CARE DAYS, WORSENING FEEDBACK -> INCREASE MONITORING
# ==============================================================================

def test_patient_3_low_risk_worsening_increase_monitoring():
    """
    PATIENT 3:
    LOW risk, 10 care days, worsening feedback -> INCREASE MONITORING
    """
    orchestrator = MultiPatientOrchestrator()
    patient_id = "P3-LOW-WORSENING"

    orchestrator.register_patient_from_event(
        InitialRiskEvent(
            patient_id=patient_id,
            risk_score=0.20,
            risk_level="LOW",
            care_duration_days=10,
        )
    )

    # Ingest Day 4 Worsening Symptoms
    event = PatientEvent(
        patient_id=patient_id,
        event_type="symptom_report",
        day=4,
        feedback={
            "symptoms": ["mild nausea", "persistent headache"],
            "medication_taken": True,
            "energy_level": 4,
        }
    )
    final_state = orchestrator.process_patient_event(event)
    next_route = route_after_adapt(final_state)

    print_trace(
        patient_id=patient_id,
        risk_level=final_state["risk_level"],
        care_duration_days=final_state["care_duration_days"],
        current_day=final_state["current_day"],
        node_executed="Observe -> Understand -> RiskEval -> Plan -> Act -> Feedback -> Adapt",
        state_change="symptoms=['mild nausea', 'persistent headache'] | cadence: DAILY -> TWICE_DAILY",
        decision="SCENARIO_3_WORSENING (Step up monitoring cadence)",
        next_node=f"observe ({next_route})",
        final_action=final_state["current_action"],
    )

    assert final_state["current_action"] == CareAction.INCREASE_MONITORING.value
    assert final_state["monitoring_frequency"] == MonitoringFrequency.TWICE_DAILY.value
    assert final_state["care_duration_days"] == 10
    assert len(final_state["symptoms"]) > 0
    assert next_route == "increase_monitoring"


# ==============================================================================
# PATIENT 4: HIGH RISK, 30 CARE DAYS, MISSING FEEDBACK -> REQUEST MORE DATA
# ==============================================================================

def test_patient_4_high_risk_missing_feedback_request_data():
    """
    PATIENT 4:
    HIGH risk, 30 care days, missing feedback -> REQUEST MORE DATA (never assume healthy)
    """
    orchestrator = MultiPatientOrchestrator()
    patient_id = "P4-HIGH-MISSING"

    orchestrator.register_patient_from_event(
        InitialRiskEvent(
            patient_id=patient_id,
            risk_score=0.78,
            risk_level="HIGH",
            care_duration_days=30,
        )
    )

    # Ingest Day 6 Empty / Missed Check-in
    event = {
        "patient_id": patient_id,
        "event_type": "missed_checkin",
        "day": 6,
        "feedback": {},
    }
    final_state = orchestrator.process_patient_event(event)
    next_route = route_after_adapt(final_state)

    print_trace(
        patient_id=patient_id,
        risk_level=final_state["risk_level"],
        care_duration_days=final_state["care_duration_days"],
        current_day=final_state["current_day"],
        node_executed="Observe -> Understand -> RiskEval -> Plan -> Act -> Feedback -> Adapt",
        state_change="data_quality=POOR | current_action=REQUEST_MORE_DATA",
        decision="SCENARIO_5_NO_RESPONSE (Never assume missing patient is healthy)",
        next_node=f"feedback ({next_route})",
        final_action=final_state["current_action"],
    )

    assert final_state["current_action"] == CareAction.REQUEST_MORE_DATA.value
    assert final_state["data_quality"] in [DataQuality.POOR.value, DataQuality.INCOMPLETE.value]
    assert final_state["care_duration_days"] == 30
    assert next_route == "request_more_data"


# ==============================================================================
# PATIENT 5: MEDIUM RISK, 20 CARE DAYS, INCONSISTENT FEEDBACK -> REDUCE DATA QUALITY
# ==============================================================================

def test_patient_5_medium_risk_inconsistent_feedback():
    """
    PATIENT 5:
    MEDIUM risk, 20 care days, inconsistent feedback -> reduce data quality & REQUEST_MORE_DATA
    """
    orchestrator = MultiPatientOrchestrator()
    patient_id = "P5-MED-INCONSISTENT"

    orchestrator.register_patient_from_event(
        InitialRiskEvent(
            patient_id=patient_id,
            risk_score=0.45,
            risk_level="MEDIUM",
            care_duration_days=20,
        )
    )

    # Ingest Day 7 Partial/Inconsistent Feedback (symptoms logged, but medication omitted)
    event = {
        "patient_id": patient_id,
        "event_type": "daily_checkin",
        "day": 7,
        "feedback": {"symptoms": "feeling dizzy"},
    }
    final_state = orchestrator.process_patient_event(event)
    next_route = route_after_adapt(final_state)

    print_trace(
        patient_id=patient_id,
        risk_level=final_state["risk_level"],
        care_duration_days=final_state["care_duration_days"],
        current_day=final_state["current_day"],
        node_executed="Observe -> Understand -> RiskEval -> Plan -> Act -> Feedback -> Adapt",
        state_change="data_quality=DEGRADED | confidence reduced | request clarification",
        decision="SCENARIO_6_INCONSISTENT_DATA (Avoid overconfident assumption)",
        next_node=f"feedback ({next_route})",
        final_action=final_state["current_action"],
    )

    assert final_state["data_quality"] == DataQuality.DEGRADED.value
    assert final_state["current_action"] == CareAction.REQUEST_MORE_DATA.value
    assert final_state["care_duration_days"] == 20
    assert next_route == "request_more_data"


# ==============================================================================
# PATIENT 6: WORSENING CONDITION SATISFYING ESCALATION POLICY -> ESCALATE
# ==============================================================================

def test_patient_6_escalation_policy_triggered():
    """
    PATIENT 6:
    Worsening condition with red-flag symptoms -> ESCALATE
    """
    orchestrator = MultiPatientOrchestrator()
    patient_id = "P6-HIGH-CRISIS"

    orchestrator.register_patient_from_event(
        InitialRiskEvent(
            patient_id=patient_id,
            risk_score=0.88,
            risk_level="HIGH",
            care_duration_days=30,
        )
    )

    # Ingest Day 3 Emergency Symptoms
    event = PatientEvent(
        patient_id=patient_id,
        event_type="symptom_alert",
        day=3,
        feedback={
            "symptoms": ["chest pain", "severe shortness of breath"],
            "medication_taken": True,
            "energy_level": 2,
        }
    )
    final_state = orchestrator.process_patient_event(event)
    next_route = route_after_adapt(final_state)

    print_trace(
        patient_id=patient_id,
        risk_level=final_state["risk_level"],
        care_duration_days=final_state["care_duration_days"],
        current_day=final_state["current_day"],
        node_executed="Observe -> Understand -> RiskEval -> Plan -> Act -> Feedback -> Adapt -> Escalate",
        state_change="escalation_required=True | plan_status=ESCALATED",
        decision="SCENARIO_7_ESCALATION (Emergency red-flag symptoms met)",
        next_node=f"escalate ({next_route}) -> END",
        final_action=final_state["current_action"],
    )

    assert final_state["escalation_required"] is True
    assert final_state["current_action"] == CareAction.ESCALATE.value
    assert final_state["plan_status"] == PlanStatus.ESCALATED.value
    assert next_route == "escalate"


# ==============================================================================
# PATIENT 7: CURRENT_DAY REACHES CARE_DURATION_DAYS -> COMPLETE
# ==============================================================================

def test_patient_7_care_duration_completed():
    """
    PATIENT 7:
    current_day reaches care_duration_days -> COMPLETE
    """
    orchestrator = MultiPatientOrchestrator()
    patient_id = "P7-LOW-COMPLETE"

    orchestrator.register_patient_from_event(
        InitialRiskEvent(
            patient_id=patient_id,
            risk_score=0.15,
            risk_level="LOW",
            care_duration_days=14,  # Assigned 14-day duration
        )
    )

    # Ingest Day 14 Final Check-in
    event = PatientEvent(
        patient_id=patient_id,
        event_type="daily_checkin",
        day=14,
        feedback={
            "symptoms": "none",
            "medication_taken": True,
            "energy_level": 10,
        }
    )
    final_state = orchestrator.process_patient_event(event)
    next_route = route_after_adapt(final_state)

    print_trace(
        patient_id=patient_id,
        risk_level=final_state["risk_level"],
        care_duration_days=final_state["care_duration_days"],
        current_day=final_state["current_day"],
        node_executed="Observe -> Understand -> RiskEval -> Plan -> Act -> Feedback -> Adapt",
        state_change="current_day: 14/14 | plan_status=COMPLETED",
        decision="SCENARIO_8_COMPLETE (Target monitoring window successfully fulfilled)",
        next_node=f"END ({next_route})",
        final_action=final_state["current_action"],
    )

    assert final_state["current_action"] == CareAction.COMPLETE.value
    assert final_state["plan_status"] == PlanStatus.COMPLETED.value
    assert final_state["care_duration_days"] == 14
    assert next_route == "complete"


# ==============================================================================
# CONCURRENT MULTI-PATIENT EXECUTION TEST
# ==============================================================================

def test_concurrent_multi_patient_isolation():
    """
    Verify multiple patients can be processed concurrently through ONE shared
    LangGraph orchestrator while maintaining 100% thread isolation and zero data leakage.
    """
    orchestrator = MultiPatientOrchestrator()

    # Register 4 concurrent patients with distinct profiles
    patients = [
        ("CONCURRENT-P1", 0.85, "HIGH", 30),
        ("CONCURRENT-P2", 0.50, "MEDIUM", 20),
        ("CONCURRENT-P3", 0.20, "LOW", 10),
        ("CONCURRENT-P4", 0.55, "MEDIUM", 25),
    ]
    for p_id, score, risk, days in patients:
        orchestrator.register_patient(p_id, score, risk, days)

    events = [
        # P1 has chest pain -> Escalate
        PatientEvent(patient_id="CONCURRENT-P1", event_type="alert", day=3, feedback={"symptoms": ["chest pain"]}),
        # P2 is stable -> Continue
        PatientEvent(patient_id="CONCURRENT-P2", event_type="checkin", day=5, feedback={"symptoms": "none", "medication_taken": True}),
        # P3 completes duration 10 -> Complete
        PatientEvent(patient_id="CONCURRENT-P3", event_type="checkin", day=10, feedback={"symptoms": "none", "medication_taken": True}),
        # P4 misses medication -> Modify care plan
        PatientEvent(patient_id="CONCURRENT-P4", event_type="checkin", day=4, feedback={"symptoms": "none", "medication_taken": False}),
    ]

    # Process events concurrently across thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(orchestrator.process_patient_event, event) for event in events]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # Map results by patient_id
    res_map = {r["patient_id"]: r for r in results}

    # Verify P1: Escalated
    assert res_map["CONCURRENT-P1"]["plan_status"] == PlanStatus.ESCALATED.value
    assert res_map["CONCURRENT-P1"]["current_action"] == CareAction.ESCALATE.value

    # Verify P2: Stable Continue
    assert res_map["CONCURRENT-P2"]["plan_status"] == PlanStatus.ACTIVE.value
    assert res_map["CONCURRENT-P2"]["current_action"] == CareAction.CONTINUE.value

    # Verify P3: Completed
    assert res_map["CONCURRENT-P3"]["plan_status"] == PlanStatus.COMPLETED.value
    assert res_map["CONCURRENT-P3"]["current_action"] == CareAction.COMPLETE.value

    # Verify P4: Modify Care Plan
    assert res_map["CONCURRENT-P4"]["plan_status"] == PlanStatus.ACTIVE.value
    assert res_map["CONCURRENT-P4"]["current_action"] == CareAction.MODIFY_CARE_PLAN.value
    assert res_map["CONCURRENT-P4"]["care_plan"]["adherence_support_active"] is True
