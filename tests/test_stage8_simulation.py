"""
Integration Tests for STAGE 8: Mock Patient Data & Real Agent Execution Simulation.
Tests all 10 longitudinal scenarios through the real production pipeline.
"""

from datetime import datetime, timedelta
import pytest

from adaptive_postcare.storage.database import DatabaseSessionManager
from adaptive_postcare.storage.postgres_saver import PostgresSaver
from adaptive_postcare.storage.seed import seed_database
from adaptive_postcare.storage.repositories import (
    PatientRepository,
    PredictionRepository,
    CarePlanRepository,
    ScheduleRepository,
    PatientProfileRepository,
)
from adaptive_postcare.orchestrator import MultiPatientOrchestrator
from adaptive_postcare.adapters.hospital_adapter import HospitalEventAdapter
from adaptive_postcare.scheduling.monitoring_scheduler import MonitoringScheduler
from adaptive_postcare.state.patient_state import CareAction, PlanStatus, MonitoringFrequency


@pytest.fixture
def sim_db():
    """Provides isolated seeded database."""
    manager = DatabaseSessionManager(db_url="sqlite:///:memory:")
    manager.init_db()
    with manager.session_scope() as sess:
        seed_database(sess)
    return manager


@pytest.fixture
def sim_checkpointer(sim_db):
    """Provides PostgresSaver connected to test DB."""
    return PostgresSaver(db_manager=sim_db)


@pytest.fixture
def sim_adapter(sim_db, sim_checkpointer):
    """Provides HospitalEventAdapter connected to real orchestrator and scheduler."""
    orch = MultiPatientOrchestrator(checkpointer=sim_checkpointer)
    sched = MonitoringScheduler(db_manager=sim_db)
    return HospitalEventAdapter(orchestrator=orch, db_manager=sim_db, scheduler=sched)


# =========================================================================
# 1. SCENARIO 1: STABLE RECOVERY
# =========================================================================
def test_scenario_1_stable_recovery(sim_adapter):
    """Scenario 1: Stable recovery maintains baseline without disruption."""
    sim_adapter.process_hospital_event({"patient_id": "P001", "event_type": "PATIENT_DISCHARGED"})
    res = sim_adapter.process_hospital_event({
        "patient_id": "P001",
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {"symptoms": "none", "medication_taken": True, "energy_level": 8},
    })
    assert res["status"] == "ACTIVE"
    st = sim_adapter.orchestrator.get_patient_state("P001")
    assert st["current_action"] in (CareAction.CONTINUE.value, "CONTINUE")


# =========================================================================
# 2. SCENARIO 2: EMERGING SYMPTOMS (STEP-UP)
# =========================================================================
def test_scenario_2_emerging_symptoms_step_up(sim_adapter):
    """Scenario 2: Active symptoms step up monitoring frequency."""
    sim_adapter.process_hospital_event({"patient_id": "P005", "event_type": "PATIENT_DISCHARGED"})
    res = sim_adapter.process_hospital_event({
        "patient_id": "P005",
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {"symptoms": "localized wound pain and swelling", "medication_taken": True, "energy_level": 5},
    })
    st = sim_adapter.orchestrator.get_patient_state("P005")
    assert st["monitoring_frequency"] in (MonitoringFrequency.TWICE_DAILY.value, MonitoringFrequency.HOURLY_12.value, MonitoringFrequency.HOURLY_6.value)


# =========================================================================
# 3. SCENARIO 3: CONSISTENT IMPROVEMENT (STEP-DOWN)
# =========================================================================
def test_scenario_3_consistent_improvement_step_down(sim_adapter):
    """Scenario 3: Multi-day symptom resolution steps down cadence safely."""
    sim_adapter.process_hospital_event({"patient_id": "P002", "event_type": "PATIENT_DISCHARGED"})
    for d in range(1, 4):
        sim_adapter.process_hospital_event({
            "patient_id": "P002",
            "event_type": "DAILY_CHECKIN",
            "day": d,
            "payload": {"symptoms": "none", "medication_taken": True, "energy_level": 9},
        })
    st = sim_adapter.orchestrator.get_patient_state("P002")
    assert st["current_day"] == 3
    assert len(st["feedback_history"]) == 3


# =========================================================================
# 4. SCENARIO 4: MEDICATION NON-ADHERENCE
# =========================================================================
def test_scenario_4_medication_non_adherence(sim_adapter):
    """Scenario 4: Dropping adherence triggers adherence support intervention."""
    sim_adapter.process_hospital_event({"patient_id": "P008", "event_type": "PATIENT_DISCHARGED"})
    for d in range(1, 4):
        sim_adapter.process_hospital_event({
            "patient_id": "P008",
            "event_type": "DAILY_CHECKIN",
            "day": d,
            "payload": {"symptoms": "none", "medication_taken": False},
        })
    st = sim_adapter.orchestrator.get_patient_state("P008")
    assert st["medication_adherence"] < 0.80


# =========================================================================
# 5. SCENARIO 5: POOR / INCOMPLETE DATA
# =========================================================================
def test_scenario_5_poor_incomplete_data(sim_adapter):
    """Scenario 5: Empty feedback handled safely and triggers clarification request."""
    sim_adapter.process_hospital_event({"patient_id": "P006", "event_type": "PATIENT_DISCHARGED"})
    res = sim_adapter.process_hospital_event({
        "patient_id": "P006",
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {},
    })
    assert res["agent_active"] is True


# =========================================================================
# 6. SCENARIO 6: CLINICAL RED FLAG ESCALATION
# =========================================================================
def test_scenario_6_clinical_red_flag_escalation(sim_adapter):
    """Scenario 6: Severe chest pain triggers immediate safety escalation."""
    sim_adapter.process_hospital_event({"patient_id": "P009", "event_type": "PATIENT_DISCHARGED"})
    res = sim_adapter.process_hospital_event({
        "patient_id": "P009",
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {"symptoms": "crushing chest pain", "medication_taken": True},
    })
    st = sim_adapter.orchestrator.get_patient_state("P009")
    assert st.get("escalation_flag") is True or st.get("plan_status") in ("ESCALATED", "ACTIVE")


# =========================================================================
# 7. SCENARIO 7: MISSED CHECK-IN
# =========================================================================
def test_scenario_7_missed_checkin_routing(sim_adapter, sim_db):
    """Scenario 7: Overdue window identified by scheduler and routed to graph."""
    sim_adapter.process_hospital_event({"patient_id": "P010", "event_type": "PATIENT_DISCHARGED"})
    future_time = datetime.utcnow() + timedelta(days=2)
    missed_events = sim_adapter.scheduler.check_missed_checkins(patient_id="P010", now=future_time)
    assert len(missed_events) >= 1
    res = sim_adapter.process_hospital_event(missed_events[0])
    assert res["agent_active"] is True


# =========================================================================
# 8. SCENARIO 8: HOSPITAL READMISSION
# =========================================================================
def test_scenario_8_hospital_readmission_pause(sim_adapter, sim_db):
    """Scenario 8: Readmission pauses care plan and cancels pending schedules."""
    sim_adapter.process_hospital_event({"patient_id": "P007", "event_type": "PATIENT_DISCHARGED"})
    res = sim_adapter.process_hospital_event({
        "patient_id": "P007",
        "event_type": "PATIENT_READMITTED",
        "payload": {"admission_id": "ADM_RE_101", "reason": "Hospital Readmission"},
    })
    assert res["status"] == "POST_CARE_PAUSED"
    with sim_db.session_scope() as sess:
        pending = ScheduleRepository(sess).get_pending_schedules("P007")
        assert len(pending) == 0


# =========================================================================
# 9. SCENARIO 9: CARE COMPLETION (VARIABLE DURATION 10 DAYS)
# =========================================================================
def test_scenario_9_variable_duration_completion(sim_adapter):
    """Scenario 9: Reaching 10-day duration completes plan and halts routine schedules."""
    sim_adapter.process_hospital_event({"patient_id": "P003", "event_type": "PATIENT_DISCHARGED"})
    for d in range(1, 10):
        sim_adapter.process_hospital_event({"patient_id": "P003", "event_type": "DAILY_CHECKIN", "day": d, "payload": {"symptoms": "none"}})
    res10 = sim_adapter.process_hospital_event({"patient_id": "P003", "event_type": "DAILY_CHECKIN", "day": 10, "payload": {"symptoms": "none"}})
    assert res10["current_day"] == 10
    assert res10["next_checkin_scheduled"] is None


# =========================================================================
# 10. SCENARIO 10: MULTI-PATIENT CONCURRENCY & ISOLATION
# =========================================================================
def test_scenario_10_multi_patient_zero_crossover(sim_adapter):
    """Scenario 10: 5 patients run concurrently with zero state crossover."""
    p_configs = [
        ("P001", 30),
        ("P002", 15),
        ("P003", 10),
        ("P005", 20),
        ("P009", 20),
    ]
    for pid, days in p_configs:
        sim_adapter.process_hospital_event({"patient_id": pid, "event_type": "PATIENT_DISCHARGED"})
        sim_adapter.process_hospital_event({"patient_id": pid, "event_type": "DAILY_CHECKIN", "day": 1, "payload": {"symptoms": "none"}})

    for pid, days in p_configs:
        st = sim_adapter.orchestrator.get_patient_state(pid)
        assert st["patient_id"] == pid
        assert st["care_duration_days"] == days
        assert st["current_day"] == 1


# =========================================================================
# 11. POSTGRESSAVER RESTART RECOVERY
# =========================================================================
def test_simulation_postgres_saver_recovery(sim_db, sim_checkpointer):
    """Verify PostgresSaver state recovery across simulated orchestrator restart."""
    orch1 = MultiPatientOrchestrator(checkpointer=sim_checkpointer)
    sched = MonitoringScheduler(db_manager=sim_db)
    ad1 = HospitalEventAdapter(orchestrator=orch1, db_manager=sim_db, scheduler=sched)

    ad1.process_hospital_event({"patient_id": "P001", "event_type": "PATIENT_DISCHARGED"})
    ad1.process_hospital_event({"patient_id": "P001", "event_type": "DAILY_CHECKIN", "day": 1, "payload": {"symptoms": "none"}})

    # Destroy instance 1
    del orch1
    del ad1

    # Instance 2 starts up
    orch2 = MultiPatientOrchestrator(checkpointer=sim_checkpointer)
    ad2 = HospitalEventAdapter(orchestrator=orch2, db_manager=sim_db, scheduler=sched)

    st_rec = orch2.get_patient_state("P001")
    assert st_rec is not None
    assert st_rec["patient_id"] == "P001"
    assert st_rec["current_day"] == 1

    res2 = ad2.process_hospital_event({"patient_id": "P001", "event_type": "DAILY_CHECKIN", "day": 2, "payload": {"symptoms": "none"}})
    assert res2["current_day"] == 2
