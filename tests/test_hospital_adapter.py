"""
Unit and integration tests for PostgreSQL Storage and HospitalEventAdapter.
Tests the complete flow from ML prediction ingestion -> PATIENT_DISCHARGED -> MultiPatientOrchestrator.
"""

import pytest
from adaptive_postcare.storage.database import DatabaseManager
from adaptive_postcare.storage.repository import StorageRepository
from adaptive_postcare.adapters.hospital_adapter import HospitalEventAdapter
from adaptive_postcare.orchestrator import MultiPatientOrchestrator
from adaptive_postcare.schemas.patient_event import EventTypeEnum


@pytest.fixture
def test_db_manager():
    """Provides an isolated in-memory SQLite database for testing."""
    return DatabaseManager(db_url="sqlite:///:memory:")


@pytest.fixture
def storage_repo(test_db_manager):
    return StorageRepository(db_manager=test_db_manager)


@pytest.fixture
def hospital_adapter(storage_repo):
    orchestrator = MultiPatientOrchestrator()
    return HospitalEventAdapter(orchestrator=orchestrator, repository=storage_repo)


def test_save_and_retrieve_readmission_prediction(storage_repo):
    """Test storing external ML model output in PostgreSQL/DB."""
    pred = storage_repo.save_prediction(
        patient_id="P_TEST_001",
        risk_score=0.78,
        risk_level="HIGH",
        recommended_care_days=20,
        model_version="v2.1.0",
    )
    assert pred["patient_id"] == "P_TEST_001"
    assert pred["risk_score"] == 0.78
    assert pred["risk_level"] == "HIGH"
    assert pred["recommended_care_days"] == 20
    assert pred["model_version"] == "v2.1.0"

    latest = storage_repo.get_latest_prediction("P_TEST_001")
    assert latest is not None
    assert latest["risk_score"] == 0.78
    assert latest["recommended_care_days"] == 20


def test_patient_admitted_lifecycle(hospital_adapter, storage_repo):
    """Test that PATIENT_ADMITTED logs the event and keeps the agent dormant."""
    result = hospital_adapter.handle_event({
        "patient_id": "P_ADMIT_01",
        "event_type": "patient_admitted",
        "timestamp": "2026-08-21T10:00:00Z",
    })
    assert result["status"] == "ADMITTED"
    assert result["agent_active"] is False

    lifecycle = storage_repo.get_patient_lifecycle("P_ADMIT_01")
    assert lifecycle == "ADMITTED"
    assert "P_ADMIT_01" not in hospital_adapter.orchestrator.list_patients()


def test_patient_discharged_triggers_agent_with_variable_duration(hospital_adapter, storage_repo):
    """Test that PATIENT_DISCHARGED queries stored ML prediction and activates the agent on a variable duration plan."""
    # 1. External ML model generates prediction
    hospital_adapter.ingest_prediction(
        patient_id="P_DISCHARGE_01",
        risk_score=0.82,
        risk_level="HIGH",
        recommended_care_days=15,  # Variable duration: 15 days
        model_version="v2.0-rf",
    )

    # 2. Hospital fires PATIENT_DISCHARGED
    result = hospital_adapter.handle_event({
        "patient_id": "P_DISCHARGE_01",
        "event_type": "patient_discharged",
    })

    assert result["status"] in ("POST_CARE_ACTIVATED", "DISCHARGED_ACTIVE")
    assert result["agent_active"] is True
    assert result["care_duration_days"] == 15
    assert result["risk_level"] == "HIGH"
    assert result["risk_score"] == 0.82

    # Verify agent state in orchestrator was initialized with 15 days (not default 30)
    agent_state = hospital_adapter.orchestrator.get_patient_state("P_DISCHARGE_01")
    assert agent_state is not None
    assert agent_state["care_duration_days"] == 15
    assert agent_state["plan_status"] in ("INITIALIZED", "ACTIVE")


def test_patient_readmitted_pauses_agent(hospital_adapter):
    """Test that PATIENT_READMITTED transitions patient plan_status to PAUSED."""
    # Setup discharged patient
    hospital_adapter.ingest_prediction(
        patient_id="P_READMIT_01",
        risk_score=0.65,
        risk_level="HIGH",
        recommended_care_days=30,
    )
    hospital_adapter.handle_event({
        "patient_id": "P_READMIT_01",
        "event_type": "patient_discharged",
    })

    # Readmission occurs
    result = hospital_adapter.handle_event({
        "patient_id": "P_READMIT_01",
        "event_type": "patient_readmitted",
    })

    assert result["status"] in ("POST_CARE_PAUSED", "READMITTED")
    assert result["agent_active"] is False
    state = hospital_adapter.orchestrator.get_patient_state("P_READMIT_01")
    assert state["plan_status"] == "PAUSED"
    assert any("Care plan PAUSED" in note for note in state["adaptation_notes"])


def test_clinical_events_through_adapter(hospital_adapter):
    """Test daily check-in and appointment missed events passing through the 7-node LangGraph."""
    # Discharge on 10-day plan
    hospital_adapter.ingest_prediction(
        patient_id="P_CLINICAL_01",
        risk_score=0.25,
        risk_level="LOW",
        recommended_care_days=10,
    )
    hospital_adapter.handle_event({
        "patient_id": "P_CLINICAL_01",
        "event_type": "patient_discharged",
    })

    # Day 1 Check-in with mild nausea
    checkin_res = hospital_adapter.handle_event({
        "patient_id": "P_CLINICAL_01",
        "event_type": "daily_checkin",
        "day": 1,
        "feedback": {
            "symptoms": ["mild nausea"],
            "medication_taken": True,
            "energy_level": 7,
        },
    })
    assert checkin_res["agent_active"] is True
    state = checkin_res["patient_state"]
    assert state["current_day"] == 1
    assert "mild nausea" in state["symptoms"]

    # Missed Appointment Event
    missed_res = hospital_adapter.handle_event({
        "patient_id": "P_CLINICAL_01",
        "event_type": "appointment_missed",
        "day": 2,
        "feedback": {"notes": "Patient missed scheduled phone checkup."},
    })
    assert missed_res["agent_active"] is True
    assert missed_res["patient_state"]["current_day"] == 2
