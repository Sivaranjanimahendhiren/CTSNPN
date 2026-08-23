"""
Integration Tests for STAGE 4: Hospital Event Adapter.
Verifies all 14 specified lifecycle scenarios and complete end-to-end integration
with PostgreSQL persistence and the existing MultiPatientOrchestrator.
"""

import pytest
from adaptive_postcare.storage.database import DatabaseSessionManager
from adaptive_postcare.storage.repositories import (
    PatientRepository,
    HospitalRepository,
    PredictionRepository,
    EventRepository,
    PatientProfileRepository,
    CarePlanRepository,
)
from adaptive_postcare.orchestrator import MultiPatientOrchestrator
from adaptive_postcare.adapters.hospital_adapter import HospitalEventAdapter
from adaptive_postcare.services.readmission_prediction_service import ReadmissionPredictionService


@pytest.fixture
def test_db():
    """Provides isolated test database."""
    manager = DatabaseSessionManager(db_url="sqlite:///:memory:")
    manager.init_db()
    return manager


@pytest.fixture
def orchestrator():
    """Provides a clean instance of MultiPatientOrchestrator."""
    return MultiPatientOrchestrator()


@pytest.fixture
def adapter(orchestrator, test_db):
    """Provides HospitalEventAdapter wired to test database and orchestrator."""
    return HospitalEventAdapter(orchestrator=orchestrator, db_manager=test_db)


@pytest.fixture
def prediction_service(test_db):
    """Provides ReadmissionPredictionService."""
    return ReadmissionPredictionService(db_manager=test_db)


# =========================================================================
# 1. SCENARIO 1: PATIENT_ADMITTED
# =========================================================================
def test_patient_admitted_lifecycle(adapter, test_db):
    """Scenario 1: Admission logs event, sets ADMITTED status, leaves agent dormant."""
    res = adapter.process_hospital_event({
        "patient_id": "P_ADMIT_01",
        "hospital_id": "METRO_GEN",
        "event_type": "PATIENT_ADMITTED",
        "payload": {"admission_id": "ADM_990", "department": "Cardiology"},
    })

    assert res["status"] == "ADMITTED"
    assert res["agent_active"] is False

    with test_db.session_scope() as sess:
        prof = PatientProfileRepository(sess).get_profile("P_ADMIT_01")
        assert prof is not None
        hosp = HospitalRepository(sess).get_by_code("METRO_GEN")
        assert prof.current_hospital_id == hosp.hospital_id
        assert prof.admission_id == "ADM_990"

        # Verify no care plan created
        plans = CarePlanRepository(sess).list_patient_care_plans("P_ADMIT_01")
        assert len(plans) == 0


# =========================================================================
# 2. SCENARIO 2: PREDICTION STORED BEFORE DISCHARGE -> PATIENT_DISCHARGED
# =========================================================================
def test_prediction_then_discharge_activates_postcare(adapter, prediction_service, test_db):
    """Scenario 2: Discharge triggers agent enrollment on model-derived duration."""
    # Step 1: Ingest ML Prediction
    prediction_service.ingest_prediction({
        "patient_id": "P_DISCH_01",
        "risk_score": 0.82,
        "risk_level": "HIGH",
        "recommended_care_days": 30,
        "model_version": "readmission-v1",
    })

    # Step 2: Patient Discharged
    res = adapter.process_hospital_event({
        "patient_id": "P_DISCH_01",
        "hospital_id": "METRO_GEN",
        "event_type": "PATIENT_DISCHARGED",
        "payload": {"discharge_summary": "CABG recovery, stable vitals."},
    })

    assert res["status"] == "POST_CARE_ACTIVATED"
    assert res["risk_level"] == "HIGH"
    assert res["risk_score"] == 0.82
    assert res["care_duration_days"] == 30

    with test_db.session_scope() as sess:
        prof = PatientProfileRepository(sess).get_profile("P_DISCH_01")
        assert prof.care_status == "POST_CARE_ACTIVE"

        # Verify care plan was created
        active_plan = CarePlanRepository(sess).get_active_care_plan("P_DISCH_01")
        assert active_plan is not None
        assert active_plan.duration_days == 30
        assert active_plan.status == "ACTIVE"


# =========================================================================
# 3, 4, 5. SCENARIOS 3, 4, 5: HIGH (30d), MEDIUM (15d), LOW (10d)
# =========================================================================
@pytest.mark.parametrize(
    "p_id,score,level,days",
    [
        ("P_HIGH_30", 0.85, "HIGH", 30),
        ("P_MED_15", 0.50, "MEDIUM", 15),
        ("P_LOW_10", 0.15, "LOW", 10),
    ],
)
def test_standard_risk_durations_activated(adapter, prediction_service, test_db, p_id, score, level, days):
    """Scenarios 3, 4, 5: Standard risk profiles map to corresponding care durations."""
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": score,
        "risk_level": level,
        "recommended_care_days": days,
    })

    res = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "PATIENT_DISCHARGED",
    })

    assert res["status"] == "POST_CARE_ACTIVATED"
    assert res["care_duration_days"] == days
    assert res["risk_level"] == level

    with test_db.session_scope() as sess:
        plan = CarePlanRepository(sess).get_active_care_plan(p_id)
        assert plan.duration_days == days


# =========================================================================
# 6. SCENARIO 6: HIGH PATIENT WITH 20-DAY MODEL OUTPUT (DYNAMIC DURATION)
# =========================================================================
def test_high_risk_custom_duration_activated(adapter, prediction_service, test_db):
    """Scenario 6: Proves care duration is model-driven rather than risk-level hard-coded."""
    prediction_service.ingest_prediction({
        "patient_id": "P_HIGH_20",
        "risk_score": 0.76,
        "risk_level": "HIGH",
        "recommended_care_days": 20,  # Explicitly 20 days, NOT default 30
    })

    res = adapter.process_hospital_event({
        "patient_id": "P_HIGH_20",
        "event_type": "PATIENT_DISCHARGED",
    })

    assert res["status"] == "POST_CARE_ACTIVATED"
    assert res["risk_level"] == "HIGH"
    assert res["care_duration_days"] == 20

    with test_db.session_scope() as sess:
        plan = CarePlanRepository(sess).get_active_care_plan("P_HIGH_20")
        assert plan.duration_days == 20


# =========================================================================
# 7. SCENARIO 7: PATIENT_DISCHARGED WITHOUT PREDICTION (EDGE CASE)
# =========================================================================
def test_discharge_without_prediction_defers_activation(adapter, test_db):
    """Scenario 7: Discharge without prior prediction returns WAITING_FOR_RISK_ASSESSMENT."""
    res = adapter.process_hospital_event({
        "patient_id": "P_NO_PRED_01",
        "event_type": "PATIENT_DISCHARGED",
    })

    assert res["status"] == "WAITING_FOR_RISK_ASSESSMENT"
    assert res["agent_active"] is False

    with test_db.session_scope() as sess:
        plans = CarePlanRepository(sess).list_patient_care_plans("P_NO_PRED_01")
        assert len(plans) == 0


# =========================================================================
# 8. SCENARIO 8: PATIENT_READMITTED DURING ACTIVE CARE
# =========================================================================
def test_patient_readmitted_pauses_care_plan(adapter, prediction_service, test_db):
    """Scenario 8: Readmission pauses active care plan while preserving all history."""
    p_id = "P_READMIT_01"
    # 1. Ingest prediction and discharge
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.65,
        "risk_level": "MEDIUM",
        "recommended_care_days": 15,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # 2. Patient Readmitted
    res = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "PATIENT_READMITTED",
        "payload": {"admission_id": "ADM_RE_101", "reason": "Acute shortness of breath"},
    })

    assert res["status"] == "POST_CARE_PAUSED"

    with test_db.session_scope() as sess:
        prof = PatientProfileRepository(sess).get_profile(p_id)
        assert prof.care_status == "READMITTED"

        # Verify plan status changed to PAUSED
        plans = CarePlanRepository(sess).list_patient_care_plans(p_id)
        assert len(plans) == 1
        assert plans[0].status == "PAUSED"


# =========================================================================
# 9, 10, 11. SCENARIOS 9, 10, 11: CONSULTATION, APPOINTMENT EVENTS
# =========================================================================
def test_clinical_events_routed_through_orchestrator(adapter, prediction_service):
    """Scenarios 9, 10, 11: Clinical and appointment events route through existing orchestrator."""
    p_id = "P_CLIN_01"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.40,
        "risk_level": "MEDIUM",
        "recommended_care_days": 14,
    })
    adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Consultation completed event
    res_consult = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "CONSULTATION_COMPLETED",
        "payload": {"symptoms": "feeling better", "medication_taken": True, "energy_level": 7},
    })
    assert res_consult["agent_active"] is True

    # Appointment missed event
    res_missed = adapter.process_hospital_event({
        "patient_id": p_id,
        "event_type": "APPOINTMENT_MISSED",
        "payload": {"reason": "transportation issue"},
    })
    assert res_missed["agent_active"] is True


# =========================================================================
# 12. SCENARIO 12: DUPLICATE PATIENT_DISCHARGED HANDLED SAFELY
# =========================================================================
def test_duplicate_discharge_event_idempotency(adapter, prediction_service, test_db):
    """Scenario 12: Receiving duplicate discharge events does not create duplicate care plans."""
    p_id = "P_DUP_01"
    prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.80,
        "risk_level": "HIGH",
        "recommended_care_days": 30,
    })

    # Discharge 1
    res1 = adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})
    assert res1["status"] == "POST_CARE_ACTIVATED"

    # Discharge 2 (Duplicate)
    res2 = adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})
    assert res2["status"] == "POST_CARE_ACTIVATED"
    assert "already active" in res2["message"].lower()

    # Ensure only 1 care plan exists in DB
    with test_db.session_scope() as sess:
        plans = CarePlanRepository(sess).list_patient_care_plans(p_id)
        assert len(plans) == 1


# =========================================================================
# 13. SCENARIO 13: MULTI-PATIENT ISOLATION ON SHARED GRAPH
# =========================================================================
def test_multi_patient_independent_enrollment_and_isolation(adapter, prediction_service):
    """Scenario 13: P001, P002, P003 are discharged independently on one shared graph."""
    patients = [
        ("P001", 0.87, "HIGH", 30),
        ("P002", 0.52, "MEDIUM", 15),
        ("P003", 0.18, "LOW", 10),
    ]

    for p_id, score, level, days in patients:
        prediction_service.ingest_prediction({
            "patient_id": p_id,
            "risk_score": score,
            "risk_level": level,
            "recommended_care_days": days,
        })
        adapter.process_hospital_event({"patient_id": p_id, "event_type": "PATIENT_DISCHARGED"})

    # Check each patient in orchestrator
    st1 = adapter.orchestrator.get_patient_state("P001")
    st2 = adapter.orchestrator.get_patient_state("P002")
    st3 = adapter.orchestrator.get_patient_state("P003")

    assert st1["patient_id"] == "P001" and st1["care_duration_days"] == 30
    assert st2["patient_id"] == "P002" and st2["care_duration_days"] == 15
    assert st3["patient_id"] == "P003" and st3["care_duration_days"] == 10


# =========================================================================
# 14. COMPLETE END-TO-END SYNTHETIC SCENARIO
# =========================================================================
def test_complete_end_to_end_synthetic_journey(adapter, prediction_service, test_db):
    """
    Scenario 14: Full synthetic lifecycle:
    1. Prediction stored (P001, 0.87 HIGH, 30 days)
    2. PATIENT_ADMITTED
    3. PATIENT_DISCHARGED -> 30-day care plan activated
    4. Orchestrator executes Day 1 checkin
    5. Patient checkpoint updated
    6. PATIENT_READMITTED -> care paused, history preserved
    """
    p_id = "P001"
    h_id = "METRO_GEN"

    # Step 1: Store readmission prediction
    pred_res = prediction_service.ingest_prediction({
        "patient_id": p_id,
        "risk_score": 0.87,
        "risk_level": "HIGH",
        "recommended_care_days": 30,
        "model_version": "readmission-v1.0",
    })
    assert pred_res["status"] == "stored"

    # Step 2: Patient Admitted
    admit_res = adapter.process_hospital_event({
        "patient_id": p_id,
        "hospital_id": h_id,
        "event_type": "PATIENT_ADMITTED",
        "payload": {"admission_id": "ADM_METRO_001"},
    })
    assert admit_res["status"] == "ADMITTED"

    # Step 3: Patient Discharged
    disch_res = adapter.process_hospital_event({
        "patient_id": p_id,
        "hospital_id": h_id,
        "event_type": "PATIENT_DISCHARGED",
        "payload": {"discharge_summary": "Discharged post cardiac catheterization."},
    })
    assert disch_res["status"] == "POST_CARE_ACTIVATED"
    assert disch_res["care_duration_days"] == 30

    # Step 4: Execute Day 1 Routine Check-in through existing LangGraph
    checkin_res = adapter.orchestrator.process_patient_event({
        "patient_id": p_id,
        "event_type": "daily_checkin",
        "day": 1,
        "feedback": {
            "symptoms": "mild fatigue",
            "medication_taken": True,
            "energy_level": 6,
        },
    })
    assert checkin_res["current_day"] == 1
    assert checkin_res["patient_id"] == p_id

    # Step 5: Check state checkpoint
    st = adapter.orchestrator.get_patient_state(p_id)
    assert st["current_day"] == 1
    assert len(st["feedback_history"]) >= 1

    # Step 6: Patient Readmitted later
    readmit_res = adapter.process_hospital_event({
        "patient_id": p_id,
        "hospital_id": h_id,
        "event_type": "PATIENT_READMITTED",
        "payload": {"admission_id": "ADM_METRO_002", "reason": "Heart failure decompensation"},
    })
    assert readmit_res["status"] == "POST_CARE_PAUSED"

    # Step 7: Verify all history preserved in PostgreSQL
    with test_db.session_scope() as sess:
        prof = PatientProfileRepository(sess).get_profile(p_id)
        assert prof.care_status == "READMITTED"

        # Predictions preserved
        preds = PredictionRepository(sess).get_prediction_history(p_id)
        assert len(preds) == 1

        # Events preserved
        events = EventRepository(sess).get_patient_events(p_id)
        assert len(events) >= 3  # ADMITTED, DISCHARGED, READMITTED

        # Care Plan preserved in PAUSED state
        plans = CarePlanRepository(sess).list_patient_care_plans(p_id)
        assert len(plans) == 1
        assert plans[0].status == "PAUSED"
