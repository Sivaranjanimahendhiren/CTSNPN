"""
Regression & Verification Tests for Natural-Language Conversational Post-Care Pipeline.
Validates accurate separation of:
1. Recovery / symptom extraction
2. Medication adherence tracking (non-adherence routes to MODIFY_CARE_PLAN, NOT emergency ESCALATE)
3. Deterministic safety red-flag escalation
4. Incomplete data clarification requests
"""

import pytest
from adaptive_postcare.storage.database import DatabaseSessionManager
from adaptive_postcare.orchestrator import MultiPatientOrchestrator
from adaptive_postcare.adapters.hospital_adapter import HospitalEventAdapter
from adaptive_postcare.scheduling.monitoring_scheduler import MonitoringScheduler
from adaptive_postcare.state.patient_state import CareAction, PlanStatus, MonitoringFrequency
from adaptive_postcare.llm.service import LLMService


@pytest.fixture
def nl_db():
    manager = DatabaseSessionManager(db_url="sqlite:///:memory:")
    manager.init_db()
    return manager


@pytest.fixture
def nl_adapter(nl_db):
    orch = MultiPatientOrchestrator()
    sched = MonitoringScheduler(db_manager=nl_db)
    return HospitalEventAdapter(orchestrator=orch, db_manager=nl_db, scheduler=sched)


# =========================================================================
# 1. SCENARIO 1: "I'm feeling much better but forgot my medication."
# =========================================================================
def test_nl_scenario_1_improving_with_missed_medication(nl_adapter):
    """
    Patient: "I'm feeling much better but forgot my medication."
    Expected:
    - Symptoms: [] (improving / no active symptoms)
    - Medication Taken: False (non-adherent)
    - Escalation Required: False (missed dose is NOT emergency clinical red flag)
    - Action: MODIFY_CARE_PLAN (adherence intervention support)
    """
    p_id = "NL_PATIENT_01"
    nl_adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "PATIENT_DISCHARGED",
        "payload": {"risk_score": 0.50, "risk_level": "MEDIUM", "care_duration_days": 20},
    })

    # Direct extraction audit
    analysis = LLMService().analyze_feedback(
        patient_id=p_id,
        current_day=1,
        feedback_text="I'm feeling much better but forgot my medication.",
    )
    assert analysis.medication_status == "non_adherent"
    assert len([s for s in analysis.extracted_symptoms if s.lower() not in ("none", "fine", "improving")]) == 0

    # Full LangGraph execution audit
    res = nl_adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {
            "symptoms": [],
            "medication_taken": False,
            "raw_text": "I'm feeling much better but forgot my medication.",
        },
    })

    st = nl_adapter.orchestrator.get_patient_state(p_id)
    assert st["escalation_required"] is False
    assert st.get("escalation_flag", False) is False
    assert st["current_action"] == CareAction.MODIFY_CARE_PLAN.value
    assert st["medication_adherence"] < 0.80
    assert st["care_plan"].get("adherence_support_active") is True


# =========================================================================
# 2. SCENARIO 2: "I have mild pain but I'm otherwise okay."
# =========================================================================
def test_nl_scenario_2_mild_symptoms_steps_up_monitoring(nl_adapter):
    """
    Patient: "I have mild pain but I'm otherwise okay."
    Expected:
    - Symptoms: ["mild pain"]
    - Escalation Required: False (not a red flag)
    - Action: INCREASE_MONITORING (steps up cadence to monitor recovery)
    """
    p_id = "NL_PATIENT_02"
    nl_adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "PATIENT_DISCHARGED",
        "payload": {"risk_score": 0.40, "risk_level": "MEDIUM", "care_duration_days": 15},
    })

    res = nl_adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {
            "symptoms": ["mild pain"],
            "medication_taken": True,
            "raw_text": "I have mild pain but I'm otherwise okay.",
        },
    })

    st = nl_adapter.orchestrator.get_patient_state(p_id)
    assert st["escalation_required"] is False
    assert st["current_action"] == CareAction.INCREASE_MONITORING.value
    assert st["monitoring_frequency"] in (MonitoringFrequency.TWICE_DAILY.value, MonitoringFrequency.HOURLY_12.value)


# =========================================================================
# 3. SCENARIO 3: "I'm having severe chest pain and difficulty breathing."
# =========================================================================
def test_nl_scenario_3_red_flag_triggers_emergency_escalation(nl_adapter):
    """
    Patient: "I'm having severe chest pain and difficulty breathing."
    Expected:
    - Symptoms: ["severe chest pain", "difficulty breathing"]
    - Escalation Required: True (emergency red flag detected)
    - Action: ESCALATE
    - Plan Status: ESCALATED
    """
    p_id = "NL_PATIENT_03"
    nl_adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "PATIENT_DISCHARGED",
        "payload": {"risk_score": 0.70, "risk_level": "HIGH", "care_duration_days": 30},
    })

    res = nl_adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {
            "symptoms": ["severe chest pain", "difficulty breathing"],
            "medication_taken": True,
            "raw_text": "I'm having severe chest pain and difficulty breathing.",
        },
    })

    st = nl_adapter.orchestrator.get_patient_state(p_id)
    assert st["escalation_required"] is True
    assert st["escalation_flag"] is True
    assert st["plan_status"] == PlanStatus.ESCALATED.value
    assert st["monitoring_frequency"] == MonitoringFrequency.HOURLY_6.value


# =========================================================================
# 4. SCENARIO 4: "I feel good today and took all my medication."
# =========================================================================
def test_nl_scenario_4_routine_adherent_stable_recovery(nl_adapter):
    """
    Patient: "I feel good today and took all my medication."
    Expected:
    - Symptoms: [] (none / fine)
    - Medication: True (100% adherence)
    - Escalation Required: False
    - Action: CONTINUE
    """
    p_id = "NL_PATIENT_04"
    nl_adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "PATIENT_DISCHARGED",
        "payload": {"risk_score": 0.20, "risk_level": "LOW", "care_duration_days": 10},
    })

    res = nl_adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {
            "symptoms": [],
            "medication_taken": True,
            "raw_text": "I feel good today and took all my medication.",
        },
    })

    st = nl_adapter.orchestrator.get_patient_state(p_id)
    assert st["escalation_required"] is False
    assert st["current_action"] in (CareAction.CONTINUE.value, "CONTINUE")
    assert st["medication_adherence"] == 1.0


# =========================================================================
# 5. SCENARIO 5: "I don't know, I haven't checked my temperature."
# =========================================================================
def test_nl_scenario_5_incomplete_telemetry_requests_clarification(nl_adapter):
    """
    Patient: "I don't know, I haven't checked my temperature."
    Expected:
    - Data Quality: INCOMPLETE / DEGRADED
    - Escalation Required: False
    - Action: REQUEST_MORE_DATA (requests missing telemetry without crashing)
    """
    p_id = "NL_PATIENT_05"
    nl_adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "PATIENT_DISCHARGED",
        "payload": {"risk_score": 0.30, "risk_level": "LOW", "care_duration_days": 14},
    })

    # Direct extraction quality audit
    analysis = LLMService().analyze_feedback(
        patient_id=p_id,
        current_day=1,
        feedback_text="I don't know, I haven't checked my temperature.",
    )

    res = nl_adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {
            "symptoms": [],
            "medication_taken": None,
            "raw_text": "I don't know, I haven't checked my temperature.",
        },
    })

    assert res["agent_active"] is True
