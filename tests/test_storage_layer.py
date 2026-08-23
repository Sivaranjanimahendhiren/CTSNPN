"""
Comprehensive Unit and Integration Tests for the PostgreSQL Storage Layer.
Tests all 8 tables, 8 repositories, constraints, foreign keys, validation rules, and seed data.
"""

import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from adaptive_postcare.storage.database import DatabaseSessionManager
from adaptive_postcare.storage.models import (
    Hospital,
    Patient,
    ReadmissionPrediction,
    HospitalEvent,
    PatientProfile,
    CarePlan,
    PatientFeedback,
    AgentAction,
)
from adaptive_postcare.storage.repositories import (
    PatientRepository,
    HospitalRepository,
    PredictionRepository,
    EventRepository,
    PatientProfileRepository,
    CarePlanRepository,
    FeedbackRepository,
    AgentActionRepository,
)
from adaptive_postcare.storage.seed import seed_database


@pytest.fixture
def db_session_manager():
    """Provides an isolated in-memory SQLite database session manager for each test."""
    manager = DatabaseSessionManager(db_url="sqlite:///:memory:")
    manager.init_db()
    return manager


@pytest.fixture
def session(db_session_manager):
    """Provides a transactional session fixture."""
    with db_session_manager.session_scope() as sess:
        yield sess


# =========================================================================
# 1. PATIENT REPOSITORY TESTS
# =========================================================================
def test_create_and_get_patient(session):
    repo = PatientRepository(session)
    patient = repo.create_patient("P_TEST_01")
    assert patient.patient_id == "P_TEST_01"
    assert patient.created_at is not None

    fetched = repo.get_patient("P_TEST_01")
    assert fetched is not None
    assert fetched.patient_id == "P_TEST_01"
    assert repo.exists("P_TEST_01") is True
    assert repo.exists("P_NON_EXISTENT") is False


def test_patient_empty_id_raises_error(session):
    repo = PatientRepository(session)
    with pytest.raises(ValueError):
        repo.create_patient("   ")


# =========================================================================
# 2. HOSPITAL REPOSITORY TESTS
# =========================================================================
def test_create_and_get_hospital(session):
    repo = HospitalRepository(session)
    hosp = repo.create_hospital(
        hospital_code="METRO_01",
        hospital_name="Metro General Hospital",
        location="New York, NY",
    )
    assert hosp.hospital_code == "METRO_01"
    assert hosp.is_active is True

    fetched = repo.get_by_code("METRO_01")
    assert fetched is not None
    assert fetched.hospital_name == "Metro General Hospital"

    # Test unique code constraint
    with pytest.raises(IntegrityError):
        repo.create_hospital(
            hospital_code="METRO_01",
            hospital_name="Duplicate Hospital",
        )
    session.rollback()


# =========================================================================
# 3. PREDICTION REPOSITORY TESTS (READMISSION MODEL OUTPUT)
# =========================================================================
def test_store_and_retrieve_readmission_prediction(session):
    p_repo = PatientRepository(session)
    p_repo.create_patient("P_PRED_01")

    pred_repo = PredictionRepository(session)
    # Flexible duration: 14 days
    pred1 = pred_repo.create_prediction(
        patient_id="P_PRED_01",
        risk_score=0.45,
        risk_level="MEDIUM",
        recommended_care_days=14,
        model_version="readmission-v1.2",
    )
    assert pred1.prediction_id is not None
    assert pred1.risk_score == 0.45
    assert pred1.recommended_care_days == 14

    # Add second prediction update
    pred2 = pred_repo.create_prediction(
        patient_id="P_PRED_01",
        risk_score=0.72,
        risk_level="HIGH",
        recommended_care_days=20,
        model_version="readmission-v2.0",
    )

    latest = pred_repo.get_latest_prediction("P_PRED_01")
    assert latest is not None
    assert latest.risk_score == 0.72
    assert latest.recommended_care_days == 20

    history = pred_repo.get_prediction_history("P_PRED_01")
    assert len(history) == 2


@pytest.mark.parametrize("invalid_score", [-0.1, 1.05, 2.0, -5.0])
def test_prediction_invalid_risk_score_bounds(session, invalid_score):
    p_repo = PatientRepository(session)
    p_repo.create_patient(f"P_INV_{abs(int(invalid_score * 100))}")
    pred_repo = PredictionRepository(session)
    with pytest.raises(ValueError):
        pred_repo.create_prediction(
            patient_id=f"P_INV_{abs(int(invalid_score * 100))}",
            risk_score=invalid_score,
            risk_level="HIGH",
            recommended_care_days=30,
        )


@pytest.mark.parametrize("invalid_duration", [0, -1, -30])
def test_prediction_invalid_care_duration_bounds(session, invalid_duration):
    p_repo = PatientRepository(session)
    p_repo.create_patient(f"P_DUR_{abs(invalid_duration)}")
    pred_repo = PredictionRepository(session)
    with pytest.raises(ValueError):
        pred_repo.create_prediction(
            patient_id=f"P_DUR_{abs(invalid_duration)}",
            risk_score=0.5,
            risk_level="MEDIUM",
            recommended_care_days=invalid_duration,
        )


# =========================================================================
# 4. HOSPITAL EVENT REPOSITORY TESTS
# =========================================================================
def test_store_and_query_hospital_events(session):
    p_repo = PatientRepository(session)
    p_repo.create_patient("P_EVT_01")
    h_repo = HospitalRepository(session)
    hosp = h_repo.create_hospital("HOSP_EVT", "Event Hospital")

    evt_repo = EventRepository(session)
    e1 = evt_repo.create_event(
        patient_id="P_EVT_01",
        hospital_id=hosp.hospital_id,
        event_type="PATIENT_ADMITTED",
        payload={"department": "ICU"},
    )
    assert e1.event_type == "PATIENT_ADMITTED"
    assert e1.payload == {"department": "ICU"}

    e2 = evt_repo.create_event(
        patient_id="P_EVT_01",
        hospital_id=hosp.hospital_id,
        event_type="PATIENT_DISCHARGED",
        payload={"discharge_summary": "Stable after surgery"},
    )

    all_events = evt_repo.get_patient_events("P_EVT_01")
    assert len(all_events) == 2
    assert all_events[0].event_type == "PATIENT_ADMITTED"
    assert all_events[1].event_type == "PATIENT_DISCHARGED"

    latest = evt_repo.get_latest_event("P_EVT_01")
    assert latest.event_type == "PATIENT_DISCHARGED"


# =========================================================================
# 5. PATIENT PROFILE REPOSITORY TESTS (CURRENT STATUS)
# =========================================================================
def test_patient_profile_lifecycle(session):
    p_repo = PatientRepository(session)
    p_repo.create_patient("P_PROF_01")

    prof_repo = PatientProfileRepository(session)
    prof = prof_repo.create_or_update_profile(
        patient_id="P_PROF_01",
        care_status="ADMITTED",
        admission_id="ADM-1001",
    )
    assert prof.care_status == "ADMITTED"
    assert prof.admission_id == "ADM-1001"

    # Transition to DISCHARGED
    updated = prof_repo.update_status("P_PROF_01", "DISCHARGED")
    assert updated.care_status == "DISCHARGED"

    # Transition to POST_CARE_ACTIVE
    active = prof_repo.update_status("P_PROF_01", "POST_CARE_ACTIVE")
    assert active.care_status == "POST_CARE_ACTIVE"


# =========================================================================
# 6. CARE PLAN REPOSITORY TESTS (VARIABLE DURATIONS)
# =========================================================================
@pytest.mark.parametrize("care_duration", [10, 14, 15, 20, 30, 45])
def test_create_care_plan_variable_durations(session, care_duration):
    p_repo = PatientRepository(session)
    p_id = f"P_PLAN_{care_duration}"
    p_repo.create_patient(p_id)

    plan_repo = CarePlanRepository(session)
    plan = plan_repo.create_care_plan(
        patient_id=p_id,
        duration_days=care_duration,
        monitoring_frequency="HOURLY_12" if care_duration >= 30 else "DAILY",
        plan_data={"target_window": care_duration},
    )
    assert plan.duration_days == care_duration
    assert plan.current_day == 0
    assert plan.status == "INITIALIZED"

    active_plan = plan_repo.get_active_care_plan(p_id)
    assert active_plan is not None
    assert active_plan.duration_days == care_duration

    # Update progress to Day 5
    updated = plan_repo.update_care_plan(
        care_plan_id=plan.care_plan_id,
        current_day=5,
        status="ACTIVE",
    )
    assert updated.current_day == 5
    assert updated.status == "ACTIVE"


# =========================================================================
# 7. PATIENT FEEDBACK REPOSITORY TESTS (JSONB PAYLOAD)
# =========================================================================
def test_store_and_query_patient_feedback(session):
    p_repo = PatientRepository(session)
    p_repo.create_patient("P_FDB_01")

    fb_repo = FeedbackRepository(session)
    fb = fb_repo.create_feedback(
        patient_id="P_FDB_01",
        day=3,
        feedback_type="DAILY_CHECKIN",
        raw_feedback="Feeling slightly tired but medication was taken.",
        structured_feedback={
            "symptoms": ["mild fatigue"],
            "medication_taken": True,
            "energy_level": 7,
        },
    )
    assert fb.day == 3
    assert fb.structured_feedback["medication_taken"] is True

    history = fb_repo.get_feedback_history("P_FDB_01")
    assert len(history) == 1
    assert history[0].structured_feedback["energy_level"] == 7


# =========================================================================
# 8. AGENT ACTION REPOSITORY TESTS (AUDIT TRAIL)
# =========================================================================
def test_record_and_query_agent_actions(session):
    p_repo = PatientRepository(session)
    p_repo.create_patient("P_ACT_01")

    action_repo = AgentActionRepository(session)
    act = action_repo.record_action(
        patient_id="P_ACT_01",
        day=4,
        node_name="Adapt",
        action_type="INCREASE_MONITORING",
        reason="Reported symptoms require higher telemetry frequency",
        tool_name="monitoring_cadence_tool",
        result={"new_frequency": "HOURLY_12", "status": "APPLIED"},
    )
    assert act.node_name == "Adapt"
    assert act.action_type == "INCREASE_MONITORING"
    assert act.result["new_frequency"] == "HOURLY_12"

    actions = action_repo.get_patient_actions("P_ACT_01")
    assert len(actions) == 1
    assert actions[0].action_type == "INCREASE_MONITORING"


# =========================================================================
# 9. SEED DATA EXECUTION TEST
# =========================================================================
def test_synthetic_seed_database_execution(session):
    stats = seed_database(session)
    assert stats["hospitals"] == 3
    assert stats["patients"] == 10
    assert stats["predictions"] == 10
    assert stats["events"] >= 10
    assert stats["care_plans"] >= 1

    # Verify patient P001 has 30 days and P002 has 15 days
    pred_repo = PredictionRepository(session)
    p1_pred = pred_repo.get_latest_prediction("P001")
    assert p1_pred.recommended_care_days == 30
    assert p1_pred.risk_level == "HIGH"

    p2_pred = pred_repo.get_latest_prediction("P002")
    assert p2_pred.recommended_care_days == 15
    assert p2_pred.risk_level == "MEDIUM"

    p3_pred = pred_repo.get_latest_prediction("P003")
    assert p3_pred.recommended_care_days == 10
    assert p3_pred.risk_level == "LOW"
