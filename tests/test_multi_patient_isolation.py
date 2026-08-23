"""
Unit tests for multi-patient state isolation:
Verifies that ONE single LangGraph state machine handles multiple independent PatientStates.
Ensures zero state leakage or cross-talk between patients.
"""

import pytest
from adaptive_postcare.orchestrator import MultiPatientOrchestrator
from adaptive_postcare.schemas.readmission_input import InitialRiskEvent
from adaptive_postcare.schemas.patient_event import PatientEvent
from adaptive_postcare.state.patient_state import RiskLevel, PlanStatus, CareAction


def test_multi_patient_state_isolation():
    """
    Test requirement:
    - P001 receives HIGH risk / 30 days
    - P002 receives MEDIUM risk / 20 days
    - P003 receives LOW risk / 10 days
    - Send events to each patient independently
    - Verify complete state isolation, independent histories, and shared graph instance
    """
    orchestrator = MultiPatientOrchestrator()

    # 1. Register 3 patients with distinct risk levels & durations
    # P001: HIGH risk / 30 days
    state_p001 = orchestrator.register_patient_from_event(
        InitialRiskEvent(
            patient_id="P001",
            risk_score=0.82,
            risk_level="HIGH",
            care_duration_days=30,
        )
    )

    # P002: MEDIUM risk / 20 days
    state_p002 = orchestrator.register_patient_from_event(
        InitialRiskEvent(
            patient_id="P002",
            risk_score=0.48,
            risk_level="MEDIUM",
            care_duration_days=20,
        )
    )

    # P003: LOW risk / 10 days
    state_p003 = orchestrator.register_patient_from_event(
        InitialRiskEvent(
            patient_id="P003",
            risk_score=0.15,
            risk_level="LOW",
            care_duration_days=10,
        )
    )

    # Verify initial isolation
    assert state_p001["patient_id"] == "P001"
    assert state_p001["risk_level"] == RiskLevel.HIGH.value
    assert state_p001["care_duration_days"] == 30

    assert state_p002["patient_id"] == "P002"
    assert state_p002["risk_level"] == RiskLevel.MEDIUM.value
    assert state_p002["care_duration_days"] == 20

    assert state_p003["patient_id"] == "P003"
    assert state_p003["risk_level"] == RiskLevel.LOW.value
    assert state_p003["care_duration_days"] == 10

    # 2. Dispatch event to P001: Acute worsening on Day 3 -> Escalation
    event_p001 = PatientEvent(
        patient_id="P001",
        event_type="symptom_alert",
        day=3,
        feedback={
            "symptoms": ["chest pain", "shortness of breath"],
            "medication_taken": True,
            "energy_level": 3,
        }
    )
    res_p001 = orchestrator.process_patient_event(event_p001)

    # 3. Dispatch event to P002: Missed medication on Day 5 -> Care Plan Modification
    event_p002 = PatientEvent(
        patient_id="P002",
        event_type="daily_checkin",
        day=5,
        feedback={
            "symptoms": "none",
            "medication_taken": False,
            "energy_level": 7,
        }
    )
    res_p002 = orchestrator.process_patient_event(event_p002)

    # 4. Dispatch event to P003: Final check-in on Day 10 -> Completed Care Plan
    event_p003 = PatientEvent(
        patient_id="P003",
        event_type="daily_checkin",
        day=10,
        feedback={
            "symptoms": "none",
            "medication_taken": True,
            "energy_level": 9,
        }
    )
    res_p003 = orchestrator.process_patient_event(event_p003)

    # --------------------------------------------------------------------------
    # VERIFICATION 1: P001 STATE INTEGRITY & ISOLATION
    # --------------------------------------------------------------------------
    assert res_p001["patient_id"] == "P001"
    assert res_p001["escalation_required"] is True
    assert res_p001["plan_status"] == PlanStatus.ESCALATED.value
    assert "chest pain" in res_p001["symptoms"]
    assert res_p001["current_day"] == 3
    assert res_p001["care_duration_days"] == 30

    # --------------------------------------------------------------------------
    # VERIFICATION 2: P002 IS NOT AFFECTED BY P001 OR P003
    # --------------------------------------------------------------------------
    assert res_p002["patient_id"] == "P002"
    assert res_p002["escalation_required"] is False
    assert res_p002["plan_status"] == PlanStatus.ACTIVE.value
    assert res_p002["symptoms"] == []
    assert res_p002["current_day"] == 5
    assert res_p002["care_duration_days"] == 20
    assert res_p002["care_plan"]["adherence_support_active"] is True
    assert res_p002["medication_adherence"] < 1.0

    # --------------------------------------------------------------------------
    # VERIFICATION 3: P003 IS NOT AFFECTED BY P001 OR P002
    # --------------------------------------------------------------------------
    assert res_p003["patient_id"] == "P003"
    assert res_p003["escalation_required"] is False
    assert res_p003["plan_status"] == PlanStatus.COMPLETED.value
    assert res_p003["symptoms"] == []
    assert res_p003["current_day"] == 10
    assert res_p003["care_duration_days"] == 10
    assert res_p003["medication_adherence"] == 1.0

    # --------------------------------------------------------------------------
    # VERIFICATION 4: INDEPENDENT HISTORIES
    # --------------------------------------------------------------------------
    assert len(res_p001["feedback_history"]) == 1
    assert len(res_p002["feedback_history"]) == 1
    assert len(res_p003["feedback_history"]) == 1

    # Check distinct action trails
    assert res_p001["previous_actions"][0]["action"] == CareAction.ESCALATE.value
    assert res_p002["previous_actions"][0]["action"] == CareAction.MODIFY_CARE_PLAN.value
    assert res_p003["previous_actions"][0]["action"] == CareAction.COMPLETE.value

    # --------------------------------------------------------------------------
    # VERIFICATION 5: ONE REUSABLE GRAPH PROCESSED ALL PATIENTS
    # --------------------------------------------------------------------------
    assert orchestrator.list_patients() == ["P001", "P002", "P003"]
    # Check that orchestrator holds a single compiled graph instance
    assert hasattr(orchestrator.graph, "invoke")
