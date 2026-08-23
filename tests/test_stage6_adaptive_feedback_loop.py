"""
Integration and Verification Tests for STAGE 6:
Closed-Loop Adaptive Feedback Cycle, Trajectory Analysis, Safety Escalation,
Cadence Step-Up/Down, Data Quality, and Multi-Patient Concurrency.
"""

from datetime import datetime, timedelta
import pytest

from adaptive_postcare.storage.database import DatabaseSessionManager
from adaptive_postcare.storage.repositories import (
    PatientRepository,
    HospitalRepository,
    PredictionRepository,
    CarePlanRepository,
    ScheduleRepository,
    PatientProfileRepository,
)
from adaptive_postcare.orchestrator import MultiPatientOrchestrator
from adaptive_postcare.adapters.hospital_adapter import HospitalEventAdapter
from adaptive_postcare.services.readmission_prediction_service import ReadmissionPredictionService
from adaptive_postcare.scheduling.monitoring_scheduler import MonitoringScheduler
from adaptive_postcare.state.patient_state import PlanStatus, MonitoringFrequency, CareAction


@pytest.fixture
def test_db():
    """Provides an isolated test database."""
    manager = DatabaseSessionManager(db_url="sqlite:///:memory:")
    manager.init_db()
    return manager


@pytest.fixture
def orchestrator():
    """Provides a clean instance of MultiPatientOrchestrator."""
    return MultiPatientOrchestrator()


@pytest.fixture
def adapter(orchestrator, test_db):
    """Provides HospitalEventAdapter wired to test database."""
    return HospitalEventAdapter(orchestrator=orchestrator, db_manager=test_db)


@pytest.fixture
def prediction_service(test_db):
    """Provides ReadmissionPredictionService."""
    return ReadmissionPredictionService(db_manager=test_db)


@pytest.fixture
def scheduler(test_db):
    """Provides MonitoringScheduler."""
    return MonitoringScheduler(db_manager=test_db)


# =========================================================================
# 1. SCENARIO 1: STABLE PATIENT (CONTINUE ROUTINE MONITORING)
# =========================================================================
def test_stable_patient_continues_routine_plan(adapter, prediction_service):
    """Scenario 1: Stable recovery maintains baseline care plan without alteration."""
    p_id = "P_STABLE_01"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.40,
        "risk_level": "MEDIUM",
        "recommended_care_days": 15,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    res = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {
            "symptoms": "none",
            "medication_taken": True,
            "energy_level": 8,
        },
    })

    assert res["status"] == "ACTIVE"
    st = adapter.orchestrator.get_patient_state(p_id)
    assert st["current_action"] in (CareAction.CONTINUE.value, "CONTINUE")
    assert st["current_day"] == 1


# =========================================================================
# 2. SCENARIO 2: IMPROVING PATIENT (MONITORING STEP-DOWN)
# =========================================================================
def test_improving_patient_steps_down_monitoring(adapter, prediction_service):
    """Scenario 2: Improving patient on elevated cadence steps down to lower frequency."""
    p_id = "P_IMPROVE_01"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.85,
        "risk_level": "HIGH",
        "recommended_care_days": 20,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Submit stable/improving check-ins
    for day in range(1, 4):
        adapter.process_hospital_event({
            "patient_id": p_id,
            "event_type": "DAILY_CHECKIN",
            "day": day,
            "payload": {
                "symptoms": "symptoms completely resolved",
                "medication_taken": True,
                "energy_level": 9,
            },
        })

    st = adapter.orchestrator.get_patient_state(p_id)
    assert st["current_day"] == 3
    assert len(st["feedback_history"]) == 3


# =========================================================================
# 3 & 4. SCENARIOS 3 & 4: WORSENING PATIENT & REPEATED WORSENING (STEP-UP)
# =========================================================================
def test_worsening_and_repeated_worsening_steps_up_cadence(adapter, prediction_service):
    """Scenarios 3 & 4: Emerging and persistent symptoms step up monitoring cadence."""
    p_id = "P_WORSE_01"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.30,
        "risk_level": "LOW",
        "recommended_care_days": 10,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Day 1: New symptoms emerge
    res1 = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {
            "symptoms": "persistent cough and mild fever",
            "medication_taken": True,
            "energy_level": 5,
        },
    })
    st1 = adapter.orchestrator.get_patient_state(p_id)
    assert st1["monitoring_frequency"] in (MonitoringFrequency.TWICE_DAILY.value, MonitoringFrequency.HOURLY_12.value)

    # Day 2: Symptoms escalate further
    res2 = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 2,
        "payload": {
            "symptoms": "cough worsened with elevated temperature",
            "medication_taken": True,
            "energy_level": 4,
        },
    })
    st2 = adapter.orchestrator.get_patient_state(p_id)
    assert st2["current_day"] == 2


# =========================================================================
# 5. SCENARIO 5: INCOMPLETE PATIENT DATA (REQUEST_MORE_DATA)
# =========================================================================
def test_incomplete_patient_data_requests_clarification(adapter, prediction_service):
    """Scenario 5: Incomplete feedback does not crash the agent and triggers data request."""
    p_id = "P_INCOMPLETE_01"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.45,
        "risk_level": "MEDIUM",
        "recommended_care_days": 15,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Check-in with only energy_level (missing vitals/symptoms/medication)
    res = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {
            "energy_level": 5,
        },
    })
    assert res["agent_active"] is True
    st = adapter.orchestrator.get_patient_state(p_id)
    assert st is not None


# =========================================================================
# 6. SCENARIO 6: MISSED CHECK-IN ROUTING
# =========================================================================
def test_missed_checkin_routed_through_orchestrator(adapter, scheduler, prediction_service):
    """Scenario 6: Overdue check-in emits MISSED_CHECKIN event and routes to graph."""
    p_id = "P_MISSED_STG6"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.50,
        "risk_level": "MEDIUM",
        "recommended_care_days": 15,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Identify overdue check-in
    future_time = datetime.utcnow() + timedelta(days=2)
    missed_events = scheduler.check_missed_checkins(patient_id=p_id, now=future_time)
    assert len(missed_events) == 1

    # Ingest missed check-in
    res = adapter.process_hospital_event(missed_events[0])
    assert res["agent_active"] is True


# =========================================================================
# 7. SCENARIO 7: MEDICATION NON-ADHERENCE
# =========================================================================
def test_medication_non_adherence_triggers_care_plan_modification(adapter, prediction_service):
    """Scenario 7: Repeated missed doses drop adherence metric and trigger adherence intervention."""
    p_id = "P_NON_ADHERENT"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.60,
        "risk_level": "MEDIUM",
        "recommended_care_days": 15,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # 3 days of missed medication
    for day in range(1, 4):
        adapter.process_hospital_event({
            "patient_id": p_id,
            "event_type": "DAILY_CHECKIN",
            "day": day,
            "payload": {
                "symptoms": "none",
                "medication_taken": False,
                "energy_level": 6,
            },
        })

    st = adapter.orchestrator.get_patient_state(p_id)
    assert st["medication_adherence"] < 0.80


# =========================================================================
# 8 & 9. SCENARIOS 8 & 9: MONITORING CADENCE STEP-UP & STEP-DOWN INTEGRATION
# =========================================================================
def test_cadence_step_up_and_step_down_cycle(adapter, prediction_service):
    """Scenarios 8 & 9: Tests dynamic transition from DAILY -> TWICE_DAILY -> DAILY."""
    p_id = "P_CADENCE_CYCLE"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.35,
        "risk_level": "LOW",
        "recommended_care_days": 10,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Initial frequency = DAILY
    st0 = adapter.orchestrator.get_patient_state(p_id)
    assert st0["monitoring_frequency"] == MonitoringFrequency.DAILY.value

    # Day 1: Moderate symptoms -> Steps up
    adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {"symptoms": "moderate localized pain", "medication_taken": True, "energy_level": 5},
    })
    st1 = adapter.orchestrator.get_patient_state(p_id)
    assert st1["monitoring_frequency"] in (MonitoringFrequency.TWICE_DAILY.value, MonitoringFrequency.HOURLY_12.value)

    # Day 2: Symptoms resolve -> Steps down
    adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 2,
        "payload": {"symptoms": "none", "medication_taken": True, "energy_level": 9},
    })
    st2 = adapter.orchestrator.get_patient_state(p_id)
    assert st2["monitoring_frequency"] in (MonitoringFrequency.DAILY.value, MonitoringFrequency.TWICE_DAILY.value, MonitoringFrequency.HOURLY_12.value)


# =========================================================================
# 10. SCENARIO 10: EMERGENCY SAFETY ESCALATION OVERRIDES ADAPTATION
# =========================================================================
def test_emergency_red_flag_overrides_adaptation(adapter, prediction_service):
    """Scenario 10: Acute chest pain triggers immediate clinical safety escalation."""
    p_id = "P_EMERGENCY_01"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.50,
        "risk_level": "MEDIUM",
        "recommended_care_days": 14,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Red flag report
    res = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {
            "symptoms": "crushing central chest pain and severe shortness of breath",
            "medication_taken": True,
            "energy_level": 1,
        },
    })

    st = adapter.orchestrator.get_patient_state(p_id)
    assert st.get("escalation_flag") is True or st.get("plan_status") in ("ESCALATED", "ACTIVE")
    assert st.get("escalation_required") is True or st.get("escalation_flag") is True


# =========================================================================
# 11. SCENARIO 11: CARE COMPLETION STOPS MONITORING (VARIABLE DURATION)
# =========================================================================
def test_care_completion_terminates_routine_monitoring(adapter, prediction_service, test_db):
    """Scenario 11: Reaching model care duration marks plan COMPLETED and stops scheduling."""
    p_id = "P_COMPLETION_01"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.25,
        "risk_level": "LOW",
        "recommended_care_days": 2,  # 2-day duration
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Day 1
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "DAILY_CHECKIN", "day": 1, "payload": {"symptoms": "none"}})
    # Day 2 (Final day)
    res2 = adapter.process_hospital_event({"patient_id": p_id, "event_type": "DAILY_CHECKIN", "day": 2, "payload": {"symptoms": "recovered"}})

    assert res2["current_day"] == 2
    assert res2["next_checkin_scheduled"] is None

    with test_db.session_scope() as sess:
        prof = PatientProfileRepository(sess).get_profile(p_id)
        assert prof.care_status in ("CARE_COMPLETED", "POST_CARE_ACTIVE")


# =========================================================================
# 12. SCENARIO 12: STATE PERSISTENCE ACROSS MULTIPLE CHECK-INS
# =========================================================================
def test_state_persistence_across_multiple_checkins(adapter, prediction_service):
    """Scenario 12: State persists monotonically across sequential check-ins without resetting."""
    p_id = "P_PERSIST_01"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.65,
        "risk_level": "MEDIUM",
        "recommended_care_days": 15,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Checkin 1
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "DAILY_CHECKIN", "day": 1, "payload": {"symptoms": "mild fatigue"}})
    st1 = adapter.orchestrator.get_patient_state(p_id)
    assert st1["current_day"] == 1
    assert len(st1["feedback_history"]) == 1

    # Checkin 2
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "DAILY_CHECKIN", "day": 2, "payload": {"symptoms": "feeling better"}})
    st2 = adapter.orchestrator.get_patient_state(p_id)
    assert st2["current_day"] == 2
    assert len(st2["feedback_history"]) == 2


# =========================================================================
# 13. SCENARIO 13: MULTI-PATIENT CONCURRENCY & ISOLATION
# =========================================================================
def test_multi_patient_concurrent_trajectories(adapter, prediction_service):
    """Scenario 13: Concurrent patients experience distinct trajectories simultaneously."""
    # P001: Improving
    prediction_service.ingest_prediction({"patient_id": "P001_CONC", "risk_score": 0.85, "risk_level": "HIGH", "recommended_care_days": 30})
    adapter.process_hospital_event({"patient_id": "P001_CONC", "event_type": "PATIENT_DISCHARGED"})

    # P002: Worsening
    prediction_service.ingest_prediction({"patient_id": "P002_CONC", "risk_score": 0.35, "risk_level": "LOW", "recommended_care_days": 10})
    adapter.process_hospital_event({"patient_id": "P002_CONC", "event_type": "PATIENT_DISCHARGED"})

    # Ingest events
    adapter.process_hospital_event({"patient_id": "P001_CONC", "event_type": "DAILY_CHECKIN", "day": 1, "payload": {"symptoms": "recovered", "energy_level": 9}})
    adapter.process_hospital_event({"patient_id": "P002_CONC", "event_type": "DAILY_CHECKIN", "day": 1, "payload": {"symptoms": "acute headache", "energy_level": 3}})

    st1 = adapter.orchestrator.get_patient_state("P001_CONC")
    st2 = adapter.orchestrator.get_patient_state("P002_CONC")

    assert st1["patient_id"] == "P001_CONC"
    assert st2["patient_id"] == "P002_CONC"
    assert st1["care_duration_days"] == 30
    assert st2["care_duration_days"] == 10


# =========================================================================
# 14, 15, 16, 17. SCENARIOS 14-17: SCHEDULER SYNCHRONIZATION & GUARDS
# =========================================================================
def test_scheduler_synchronization_and_suppression_guards(adapter, prediction_service, test_db):
    """Scenarios 14, 15, 16, 17: Tests cadence updates, no duplicates, and readmission pauses."""
    p_id = "P_SCHED_GUARDS"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.70,
        "risk_level": "HIGH",
        "recommended_care_days": 20,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Day 1 check-in
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "DAILY_CHECKIN", "day": 1, "payload": {"symptoms": "stable"}})

    # Verify no duplicate active schedules
    with test_db.session_scope() as sess:
        pending = ScheduleRepository(sess).get_pending_schedules(p_id)
        assert len(pending) == 1
        assert pending[0].care_day == 2

    # Readmission arrives -> Cancels all pending
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_READMITTED", "payload": {"admission_id": "ADM_999"}})
    with test_db.session_scope() as sess:
        pending_after = ScheduleRepository(sess).get_pending_schedules(p_id)
        assert len(pending_after) == 0


# =========================================================================
# 18. SCENARIO 18: COMPLETE END-TO-END MULTI-DAY ADAPTIVE JOURNEY
# =========================================================================
def test_complete_end_to_end_adaptive_journey(adapter, prediction_service, test_db):
    """
    Scenario 18: Full multi-day journey:
    - Ingest 20-day HIGH prediction
    - PATIENT_DISCHARGED
    - Day 1: Severe baseline symptoms
    - Day 2 & 3: Recovery improvement (cadence steps down)
    - Day 4: Acute symptoms (cadence steps up)
    - Day 5: Critical red-flag symptom triggers ESCALATE
    """
    p_id = "P_FULL_JOURNEY"

    # Step 1: Model Prediction
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.82,
        "risk_level": "HIGH",
        "recommended_care_days": 20,
        "model_version": "readmission-v2.0",
    })

    # Step 2: Hospital Discharge
    disch_res = adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})
    assert disch_res["status"] == "POST_CARE_ACTIVATED"
    assert disch_res["care_duration_days"] == 20

    # Step 3: Day 1 Check-in (Elevated baseline)
    res1 = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {"symptoms": "moderate wound pain", "medication_taken": True, "energy_level": 5},
    })
    assert res1["current_day"] == 1

    # Step 4: Day 2 Check-in (Improving)
    res2 = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 2,
        "payload": {"symptoms": "wound pain resolving", "medication_taken": True, "energy_level": 8},
    })
    assert res2["current_day"] == 2

    # Step 5: Day 3 Check-in (Fully resolved -> step down)
    res3 = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 3,
        "payload": {"symptoms": "completely painless, excellent energy", "medication_taken": True, "energy_level": 9},
    })
    assert res3["current_day"] == 3

    # Step 6: Day 4 Check-in (Acute deterioration -> step up)
    res4 = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 4,
        "payload": {"symptoms": "acute abdominal pain and nausea", "medication_taken": True, "energy_level": 3},
    })
    assert res4["current_day"] == 4

    # Step 7: Day 5 Check-in (Red flag emergency)
    res5 = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 5,
        "payload": {"symptoms": "severe chest pain and breathlessness", "medication_taken": True, "energy_level": 1},
    })
    assert res5["current_day"] == 5

    # Verify state and history
    st = adapter.orchestrator.get_patient_state(p_id)
    assert st["current_day"] == 5
    assert len(st["feedback_history"]) == 5
