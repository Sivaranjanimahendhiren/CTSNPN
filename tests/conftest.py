"""
Pytest fixtures and test setup for Adaptive Post-Care Agent.
"""

import pytest
from adaptive_postcare.state.patient_state import (
    PatientState,
    PatientStateModel,
    RiskLevel,
    PlanStatus,
    DataQuality,
    MonitoringFrequency,
)
from adaptive_postcare.schemas.readmission_input import ReadmissionModelInput, RiskLevelEnum
from adaptive_postcare.schemas.patient_event import PatientEvent, EventTypeEnum


@pytest.fixture
def sample_readmission_input() -> ReadmissionModelInput:
    return ReadmissionModelInput(
        patient_id="PT-10023",
        risk_score=0.78,
        risk_level=RiskLevelEnum.HIGH,
        care_duration_days=45,  # Variable duration
        model_metadata={"top_features": ["charlson_index", "previous_admissions"]}
    )


@pytest.fixture
def sample_patient_event() -> PatientEvent:
    return PatientEvent(
        event_id="EVT-001",
        patient_id="PT-10023",
        event_type=EventTypeEnum.SYMPTOM_REPORT,
        data={"symptoms": ["mild shortness of breath", "fatigue"]}
    )


@pytest.fixture
def initial_patient_state(sample_readmission_input) -> PatientState:
    model = PatientStateModel.initialize_from_external_model(
        patient_id=sample_readmission_input.patient_id,
        risk_score=sample_readmission_input.risk_score,
        risk_level=sample_readmission_input.risk_level.value,
        care_duration_days=sample_readmission_input.care_duration_days,
    )
    return model.to_state_dict()
