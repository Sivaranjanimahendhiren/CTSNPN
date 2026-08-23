"""
Comprehensive unit tests for PatientState creation, validation, and multi-event preservation.
"""

import pytest
from pydantic import ValidationError
from adaptive_postcare.state.patient_state import (
    PatientStateModel,
    RiskLevel,
    PlanStatus,
    DataQuality,
    MonitoringFrequency,
)


def test_patient_state_creation_valid():
    """Test standard state creation with valid parameters."""
    state = PatientStateModel(
        patient_id="PT-101",
        risk_score=0.65,
        risk_level=RiskLevel.HIGH,
        care_duration_days=45,  # Variable duration != 30 days
        current_day=5,
        last_checkin_day=4,
        monitoring_frequency=MonitoringFrequency.HOURLY_12,
        care_plan={"goals": ["Manage blood pressure", "Post-op wound care"]},
        symptoms=["mild dizziness"],
        medication_adherence=0.9,
        data_quality=DataQuality.GOOD,
        current_action="MONITOR_VITALS",
        next_action="SCHEDULE_CALL",
        escalation_required=False,
        previous_actions=[{"action": "INITIAL_SURVEY", "status": "COMPLETED"}],
        latest_feedback="Feeling slightly tired but better",
        feedback_history=[{"day": 2, "content": "Pain level 4/10"}],
        plan_status=PlanStatus.ACTIVE,
    )

    assert state.patient_id == "PT-101"
    assert state.risk_score == 0.65
    assert state.risk_level == RiskLevel.HIGH
    assert state.care_duration_days == 45
    assert state.current_day == 5
    assert state.last_checkin_day == 4
    assert state.monitoring_frequency == MonitoringFrequency.HOURLY_12
    assert state.medication_adherence == 0.9
    assert state.plan_status == PlanStatus.ACTIVE


@pytest.mark.parametrize("duration", [7, 14, 21, 45, 60, 90, 180])
def test_variable_care_duration(duration: int):
    """Verifies that care duration is flexible and not fixed to 30 days."""
    state = PatientStateModel.initialize_from_external_model(
        patient_id=f"PT-DUR-{duration}",
        risk_score=0.4,
        risk_level="MEDIUM",
        care_duration_days=duration,
    )
    assert state.care_duration_days == duration
    assert state.current_day == 0


def test_initialize_from_external_model_risk_frequency_mapping():
    """Test factory initialization and appropriate monitoring frequency defaults."""
    critical_state = PatientStateModel.initialize_from_external_model(
        patient_id="PT-CRIT",
        risk_score=0.92,
        risk_level="CRITICAL",
        care_duration_days=14,
    )
    assert critical_state.risk_level == RiskLevel.CRITICAL
    assert critical_state.monitoring_frequency == MonitoringFrequency.HOURLY_6
    assert critical_state.escalation_required is True

    low_state = PatientStateModel.initialize_from_external_model(
        patient_id="PT-LOW",
        risk_score=0.15,
        risk_level="LOW",
        care_duration_days=60,
    )
    assert low_state.risk_level == RiskLevel.LOW
    assert low_state.monitoring_frequency == MonitoringFrequency.DAILY
    assert low_state.escalation_required is False


def test_invalid_risk_level():
    """Test that invalid risk level values raise ValidationError."""
    with pytest.raises(ValidationError):
        PatientStateModel(
            patient_id="PT-ERR",
            risk_score=0.5,
            risk_level="UNKNOWN_LEVEL",
            care_duration_days=30,
        )


@pytest.mark.parametrize("invalid_duration", [0, -1, -30])
def test_invalid_care_duration(invalid_duration: int):
    """Test that non-positive care durations raise ValidationError."""
    with pytest.raises(ValidationError):
        PatientStateModel(
            patient_id="PT-ERR",
            risk_score=0.5,
            risk_level=RiskLevel.MEDIUM,
            care_duration_days=invalid_duration,
        )


def test_current_day_exceeds_care_duration():
    """Test invariant: current_day cannot exceed care_duration_days."""
    with pytest.raises(ValidationError, match="cannot exceed care_duration_days"):
        PatientStateModel(
            patient_id="PT-ERR",
            risk_score=0.5,
            risk_level=RiskLevel.MEDIUM,
            care_duration_days=15,
            current_day=16,
        )


def test_last_checkin_day_exceeds_current_day():
    """Test invariant: last_checkin_day cannot exceed current_day."""
    with pytest.raises(ValidationError, match="cannot exceed current_day"):
        PatientStateModel(
            patient_id="PT-ERR",
            risk_score=0.5,
            risk_level=RiskLevel.MEDIUM,
            care_duration_days=30,
            current_day=3,
            last_checkin_day=4,
        )


@pytest.mark.parametrize("invalid_score", [-0.1, 1.1, 2.0])
def test_risk_score_bounds(invalid_score: float):
    """Test risk_score must be between 0.0 and 1.0."""
    with pytest.raises(ValidationError):
        PatientStateModel(
            patient_id="PT-ERR",
            risk_score=invalid_score,
            risk_level=RiskLevel.LOW,
            care_duration_days=30,
        )


@pytest.mark.parametrize("invalid_adh", [-0.5, 1.5])
def test_medication_adherence_bounds(invalid_adh: float):
    """Test medication_adherence must be between 0.0 and 1.0."""
    with pytest.raises(ValidationError):
        PatientStateModel(
            patient_id="PT-ERR",
            risk_score=0.3,
            risk_level=RiskLevel.LOW,
            care_duration_days=30,
            medication_adherence=invalid_adh,
        )


def test_invalid_plan_status_and_data_quality():
    """Test validation for status fields."""
    with pytest.raises(ValidationError):
        PatientStateModel(
            patient_id="PT-ERR",
            risk_score=0.3,
            risk_level=RiskLevel.LOW,
            care_duration_days=30,
            plan_status="INVALID_STATUS",
        )

    with pytest.raises(ValidationError):
        PatientStateModel(
            patient_id="PT-ERR",
            risk_score=0.3,
            risk_level=RiskLevel.LOW,
            care_duration_days=30,
            data_quality="SUPER_GOOD",
        )


def test_state_preservation_across_events():
    """Test evolving the patient state across multiple discrete events."""
    # 1. Day 0: Initial state from external model
    state = PatientStateModel.initialize_from_external_model(
        patient_id="PT-EVOLVE-01",
        risk_score=0.60,
        risk_level=RiskLevel.MEDIUM,
        care_duration_days=21,
    )
    assert state.current_day == 0
    assert len(state.previous_actions) == 0
    assert len(state.feedback_history) == 0

    # 2. Day 1 Event: First Check-in with mild symptom
    state_dict = state.to_state_dict()
    state_dict["current_day"] = 1
    state_dict["last_checkin_day"] = 1
    state_dict["symptoms"].append("mild swelling")
    state_dict["latest_feedback"] = "Mild ankle swelling noted this morning"
    state_dict["feedback_history"].append({"day": 1, "note": "Mild swelling"})
    state_dict["previous_actions"].append({"action": "SEND_CHECKIN_SMS", "day": 1, "status": "DELIVERED"})
    state_dict["plan_status"] = PlanStatus.ACTIVE.value

    # Re-validate updated state
    updated_state_day1 = PatientStateModel(**state_dict)
    assert updated_state_day1.current_day == 1
    assert "mild swelling" in updated_state_day1.symptoms
    assert len(updated_state_day1.previous_actions) == 1
    assert len(updated_state_day1.feedback_history) == 1

    # 3. Day 3 Event: Second Check-in with medication side effect
    state_dict_2 = updated_state_day1.to_state_dict()
    state_dict_2["current_day"] = 3
    state_dict_2["last_checkin_day"] = 3
    state_dict_2["symptoms"].append("nausea")
    state_dict_2["medication_adherence"] = 0.8
    state_dict_2["latest_feedback"] = "Missed morning dose due to nausea"
    state_dict_2["feedback_history"].append({"day": 3, "note": "Nausea / missed dose"})
    state_dict_2["previous_actions"].append({"action": "NURSE_CALLBACK", "day": 3, "status": "COMPLETED"})

    updated_state_day3 = PatientStateModel(**state_dict_2)
    assert updated_state_day3.current_day == 3
    assert updated_state_day3.last_checkin_day == 3
    assert len(updated_state_day3.symptoms) == 2
    assert len(updated_state_day3.feedback_history) == 2
    assert len(updated_state_day3.previous_actions) == 2
    assert updated_state_day3.medication_adherence == 0.8
