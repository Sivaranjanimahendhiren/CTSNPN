"""
Unit tests for agent input schemas:
- INPUT 1: InitialRiskEvent (from external ML readmission model)
- INPUT 2: PatientEvent (during care journey)
"""

import pytest
from pydantic import ValidationError
from adaptive_postcare.schemas.readmission_input import (
    InitialRiskEvent,
    RiskLevelEnum,
)
from adaptive_postcare.schemas.patient_event import (
    PatientEvent,
    CheckinFeedback,
    EventTypeEnum,
)


# ==============================================================================
# INPUT 1: INITIAL_RISK_EVENT TESTS
# ==============================================================================

def test_initial_risk_event_valid_example():
    """Verify the exact user-specified example for INPUT 1."""
    data = {
        "patient_id": "P001",
        "risk_score": 0.82,
        "risk_level": "HIGH",
        "care_duration_days": 30,
    }
    event = InitialRiskEvent(**data)
    assert event.patient_id == "P001"
    assert event.risk_score == 0.82
    assert event.risk_level == RiskLevelEnum.HIGH
    assert event.care_duration_days == 30


@pytest.mark.parametrize("score,level,duration", [
    (0.0, "LOW", 7),
    (0.45, "MEDIUM", 14),
    (0.75, "HIGH", 45),
    (1.0, "CRITICAL", 90),
    (0.35, "low", 21),       # case-insensitive parsing
    (0.88, "critical", 15),  # case-insensitive parsing
])
def test_initial_risk_event_valid_variations(score: float, level: str, duration: int):
    """Test valid variations including score boundaries and non-fixed durations."""
    event = InitialRiskEvent(
        patient_id="PT-TEST",
        risk_score=score,
        risk_level=level,  # type: ignore
        care_duration_days=duration,
    )
    assert event.risk_score == score
    assert event.risk_level == RiskLevelEnum(level.upper())
    assert event.care_duration_days == duration


@pytest.mark.parametrize("invalid_patient_id", ["", "   ", None])
def test_initial_risk_event_invalid_patient_id(invalid_patient_id):
    """Ensure empty or whitespace-only patient_id is rejected."""
    with pytest.raises(ValidationError):
        InitialRiskEvent(
            patient_id=invalid_patient_id,  # type: ignore
            risk_score=0.5,
            risk_level=RiskLevelEnum.MEDIUM,
            care_duration_days=30,
        )


@pytest.mark.parametrize("invalid_score", [-0.01, 1.01, -5.0, 99.0])
def test_initial_risk_event_invalid_score_bounds(invalid_score: float):
    """Ensure risk_score strictly requires 0.0 <= score <= 1.0."""
    with pytest.raises(ValidationError):
        InitialRiskEvent(
            patient_id="P001",
            risk_score=invalid_score,
            risk_level=RiskLevelEnum.MEDIUM,
            care_duration_days=30,
        )


def test_initial_risk_event_invalid_risk_level():
    """Ensure invalid risk tier strings are rejected."""
    with pytest.raises(ValidationError, match="Invalid risk_level"):
        InitialRiskEvent(
            patient_id="P001",
            risk_score=0.5,
            risk_level="VERY_HIGH",  # type: ignore
            care_duration_days=30,
        )


@pytest.mark.parametrize("invalid_duration", [0, -1, -30])
def test_initial_risk_event_invalid_duration(invalid_duration: int):
    """Ensure care duration must be >= 1."""
    with pytest.raises(ValidationError, match="care_duration_days must be >= 1"):
        InitialRiskEvent(
            patient_id="P001",
            risk_score=0.5,
            risk_level=RiskLevelEnum.LOW,
            care_duration_days=invalid_duration,
        )


# ==============================================================================
# INPUT 2: PATIENT_EVENT TESTS
# ==============================================================================

def test_patient_event_valid_example():
    """Verify the exact user-specified example for INPUT 2."""
    data = {
        "patient_id": "P001",
        "event_type": "daily_checkin",
        "day": 5,
        "feedback": {
            "symptoms": "improving",
            "medication_taken": True,
            "energy_level": 7
        }
    }
    event = PatientEvent(**data)
    assert event.patient_id == "P001"
    assert event.event_type == EventTypeEnum.DAILY_CHECKIN
    assert event.day == 5
    assert isinstance(event.feedback, CheckinFeedback)
    assert event.feedback.symptoms == "improving"
    assert event.feedback.medication_taken is True
    assert event.feedback.energy_level == 7
    assert event.get_symptoms_list() == ["improving"]


def test_patient_event_symptoms_list_extraction():
    """Test get_symptoms_list with multiple symptoms and empty states."""
    event_multi = PatientEvent(
        patient_id="P002",
        day=2,
        feedback={"symptoms": ["cough", "headache", " "]}
    )
    assert event_multi.get_symptoms_list() == ["cough", "headache"]

    event_empty = PatientEvent(
        patient_id="P002",
        day=2,
        feedback={"medication_taken": True}
    )
    assert event_empty.get_symptoms_list() == []


@pytest.mark.parametrize("invalid_patient_id", ["", "  ", None])
def test_patient_event_invalid_patient_id(invalid_patient_id):
    """Ensure empty patient_id is rejected."""
    with pytest.raises(ValidationError):
        PatientEvent(
            patient_id=invalid_patient_id,  # type: ignore
            day=1,
            feedback={}
        )


@pytest.mark.parametrize("invalid_day", [-1, -10])
def test_patient_event_invalid_negative_day(invalid_day: int):
    """Ensure negative journey days are rejected."""
    with pytest.raises(ValidationError, match="day cannot be negative"):
        PatientEvent(
            patient_id="P001",
            day=invalid_day,
            feedback={}
        )


@pytest.mark.parametrize("invalid_energy", [0, 11, -5, 20])
def test_patient_event_invalid_energy_level_bounds(invalid_energy: int):
    """Ensure energy_level is bounded between 1 and 10."""
    with pytest.raises(ValidationError):
        PatientEvent(
            patient_id="P001",
            day=3,
            feedback={"energy_level": invalid_energy}
        )


def test_patient_event_custom_extra_feedback_fields():
    """Ensure additional arbitrary telemetry in feedback is cleanly accepted."""
    event = PatientEvent(
        patient_id="P001",
        event_type="vitals_submission",
        day=4,
        feedback={
            "systolic_bp": 128,
            "diastolic_bp": 82,
            "heart_rate": 72,
            "symptoms": "feeling stable",
            "medication_taken": True,
        }
    )
    assert event.feedback.symptoms == "feeling stable"
    # Extra field accessible
    assert event.feedback.model_extra["systolic_bp"] == 128
