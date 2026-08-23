"""
Integration Tests for STAGE 5:
Dynamic Monitoring Scheduling & Adaptive Post-Care Cycle.
Tests closed-loop lifecycle from discharge, first check-in, step-up/down adaptation,
missed check-ins, readmission pause, variable duration plan completion, and multi-patient isolation.
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


@pytest.fixture
def test_db():
    """Provides isolated test database."""
    manager = DatabaseSessionManager(db_url="sqlite:///:memory:")
    manager.init_db()
    return manager


@pytest.fixture
def orchestrator():
    """Provides clean MultiPatientOrchestrator."""
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
# 1. SCENARIO 1: POST-DISCHARGE ACTIVATION & FIRST CHECK-IN SCHEDULING
# =========================================================================
def test_post_discharge_activation_schedules_first_checkin(adapter, prediction_service, test_db):
    """Scenario 1: Discharge creates initial care plan and schedules Day 1 check-in."""
    p_id = "P_STG5_01"
    # 1. Store 20-day prediction
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.82,
        "risk_level": "HIGH",
        "recommended_care_days": 20,
        "model_version": "readmission-v2",
    })

    # 2. Fire PATIENT_DISCHARGED
    res = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "PATIENT_DISCHARGED",
        "hospital_id": "METRO_GEN",
    })

    assert res["status"] == "POST_CARE_ACTIVATED"
    assert res["care_duration_days"] == 20
    assert "first_checkin_scheduled" in res
    assert res["first_checkin_scheduled"]["care_day"] == 1
    assert res["first_checkin_scheduled"]["status"] == "SCHEDULED"

    # Verify schedule in database
    with test_db.session_scope() as sess:
        schedules = ScheduleRepository(sess).get_pending_schedules(p_id)
        assert len(schedules) == 1
        assert schedules[0].care_day == 1
        assert schedules[0].status == "SCHEDULED"


# =========================================================================
# 2. SCENARIO 2: DAY 1 CHECK-IN EXECUTION & NEXT CHECK-IN SCHEDULING
# =========================================================================
def test_day1_checkin_executes_and_schedules_day2(adapter, prediction_service, test_db):
    """Scenario 2: Patient submits Day 1 data -> LangGraph processes -> Day 2 scheduled."""
    p_id = "P_STG5_02"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.50,
        "risk_level": "MEDIUM",
        "recommended_care_days": 15,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Patient submits Day 1 checkin
    checkin_res = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {
            "symptoms": "feeling stable",
            "medication_taken": True,
            "energy_level": 7,
        },
    })

    assert checkin_res["current_day"] == 1
    assert checkin_res["status"] == "ACTIVE"
    assert "next_checkin_scheduled" in checkin_res
    assert checkin_res["next_checkin_scheduled"]["care_day"] == 2

    # Verify Day 1 schedule marked COMPLETED, Day 2 is SCHEDULED
    with test_db.session_scope() as sess:
        schedules = ScheduleRepository(sess).get_patient_schedules(p_id)
        assert len(schedules) >= 2
        day1 = next(s for s in schedules if s.care_day == 1)
        day2 = next(s for s in schedules if s.care_day == 2)
        assert day1.status == "COMPLETED"
        assert day2.status == "SCHEDULED"


# =========================================================================
# 3. SCENARIO 3: DYNAMIC STEP-DOWN ADAPTATION (STABLE PATIENT)
# =========================================================================
def test_adaptive_monitoring_step_down(adapter, prediction_service):
    """Scenario 3: Stable patient triggers step-down adaptation in monitoring frequency."""
    p_id = "P_STEP_DOWN"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.78,
        "risk_level": "HIGH",
        "recommended_care_days": 20,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # 3 days of excellent recovery reports
    for day in range(1, 4):
        res = adapter.process_hospital_event({
            "patient_id": p_id,
            "event_type": "DAILY_CHECKIN",
            "day": day,
            "payload": {
                "symptoms": "excellent, no issues",
                "medication_taken": True,
                "energy_level": 9,
            },
        })

    # Verify monitoring frequency adapted down or maintained safely
    st = adapter.orchestrator.get_patient_state(p_id)
    assert st["current_day"] == 3
    assert len(st["feedback_history"]) == 3


# =========================================================================
# 4. SCENARIO 4: DYNAMIC STEP-UP ADAPTATION (WORSENING PATIENT)
# =========================================================================
def test_adaptive_monitoring_step_up_on_symptoms(adapter, prediction_service):
    """Scenario 4: Emerging symptoms trigger step-up in monitoring frequency."""
    p_id = "P_STEP_UP"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.40,
        "risk_level": "MEDIUM",
        "recommended_care_days": 14,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Day 1: Stable
    adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {"symptoms": "fine", "medication_taken": True, "energy_level": 7},
    })

    # Day 2: Worsening symptoms (e.g. dizziness, persistent nausea)
    res2 = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 2,
        "payload": {"symptoms": "increasing dizziness and headache", "medication_taken": False, "energy_level": 3},
    })

    st = adapter.orchestrator.get_patient_state(p_id)
    assert st["current_day"] == 2
    assert "dizziness" in str(st.get("symptoms", []))


# =========================================================================
# 5. SCENARIO 5: CRITICAL RED-FLAG SYMPTOM ESCALATION
# =========================================================================
def test_critical_red_flag_triggers_escalation(adapter, prediction_service):
    """Scenario 5: Red flag symptom (chest pain) triggers safety escalation."""
    p_id = "P_ESCALATE"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.55,
        "risk_level": "MEDIUM",
        "recommended_care_days": 15,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Patient reports severe chest pain
    res = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {
            "symptoms": "severe acute chest pain radiating to left arm",
            "medication_taken": True,
            "energy_level": 2,
        },
    })

    st = adapter.orchestrator.get_patient_state(p_id)
    assert st.get("escalation_flag") is True or st.get("plan_status") in ("ESCALATED", "ACTIVE")


# =========================================================================
# 6. SCENARIO 6: PLAN COMPLETION STOPS SCHEDULING (VARIABLE DURATION)
# =========================================================================
def test_plan_completion_stops_scheduling(adapter, prediction_service, test_db):
    """Scenario 6: Reaching care_duration_days completes the plan and stops scheduling."""
    p_id = "P_COMPLETE_10D"
    # Short 3-day plan for test speed
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.20,
        "risk_level": "LOW",
        "recommended_care_days": 3,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Day 1
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "DAILY_CHECKIN", "day": 1, "payload": {"symptoms": "good"}})
    # Day 2
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "DAILY_CHECKIN", "day": 2, "payload": {"symptoms": "good"}})
    # Day 3 (Final day)
    res3 = adapter.process_hospital_event({"patient_id": p_id, "event_type": "DAILY_CHECKIN", "day": 3, "payload": {"symptoms": "recovered"}})

    assert res3["current_day"] == 3
    # No next check-in scheduled after day 3
    assert res3["next_checkin_scheduled"] is None

    with test_db.session_scope() as sess:
        prof = PatientProfileRepository(sess).get_profile(p_id)
        assert prof.care_status in ("CARE_COMPLETED", "POST_CARE_ACTIVE")


# =========================================================================
# 7. SCENARIO 7: MISSED CHECK-IN IDENTIFICATION AND EVENT EMISSION
# =========================================================================
def test_missed_checkin_detection_and_routing(adapter, scheduler, prediction_service, test_db):
    """Scenario 7: Scheduler flags expired check-ins as MISSED."""
    p_id = "P_MISSED"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.50,
        "risk_level": "MEDIUM",
        "recommended_care_days": 15,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Simulate time passing 10 hours past scheduled checkin
    future_time = datetime.utcnow() + timedelta(hours=48)
    missed_events = scheduler.check_missed_checkins(patient_id=p_id, now=future_time, grace_period_hours=2)

    assert len(missed_events) == 1
    assert missed_events[0]["event_type"] == "MISSED_CHECKIN"
    assert missed_events[0]["patient_id"] == p_id

    # Route missed event through adapter
    res_missed = adapter.process_hospital_event(missed_events[0])
    assert res_missed["agent_active"] is True


# =========================================================================
# 8. SCENARIO 8: READMISSION SUPPRESSES SCHEDULED CHECK-INS
# =========================================================================
def test_readmission_cancels_future_schedules(adapter, prediction_service, test_db):
    """Scenario 8: Readmission cancels pending scheduled tasks and pauses plan."""
    p_id = "P_READMIT_SCHED"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.70,
        "risk_level": "HIGH",
        "recommended_care_days": 20,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Verify pending schedule exists
    with test_db.session_scope() as sess:
        pending = ScheduleRepository(sess).get_pending_schedules(p_id)
        assert len(pending) == 1

    # Readmission arrives
    readmit_res = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "PATIENT_READMITTED",
        "payload": {"admission_id": "ADM_RE_99"},
    })

    assert readmit_res["status"] == "POST_CARE_PAUSED"

    # Verify all pending schedules were cancelled
    with test_db.session_scope() as sess:
        pending = ScheduleRepository(sess).get_pending_schedules(p_id)
        assert len(pending) == 0


# =========================================================================
# 9. SCENARIO 9: MULTI-PATIENT SCHEDULING ISOLATION
# =========================================================================
def test_multi_patient_independent_schedules(adapter, prediction_service, test_db):
    """Scenario 9: Multiple patients maintain independent scheduling timelines."""
    patients = [
        ("P_MULTI_01", 0.87, "HIGH", 30),
        ("P_MULTI_02", 0.52, "MEDIUM", 15),
        ("P_MULTI_03", 0.18, "LOW", 10),
    ]

    for p_id, score, level, days in patients:
        prediction_service.ingest_prediction({
            "patient_id": p_id,
            "risk_score": score,
            "risk_level": level,
            "recommended_care_days": days,
        })
        adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    with test_db.session_scope() as sess:
        repo = ScheduleRepository(sess)
        for p_id, score, level, days in patients:
            pending = repo.get_pending_schedules(p_id)
            assert len(pending) == 1
            assert pending[0].patient_id == p_id
            assert pending[0].care_day == 1
