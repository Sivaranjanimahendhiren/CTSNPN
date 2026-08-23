"""
Unit tests for the Care Plan Agent across LOW, MEDIUM, HIGH, and CRITICAL risk inputs.
Verifies that care durations are variable (NOT fixed to 30 days) and medical thresholds
are strictly governed by clinical policy without LLM hallucination.
"""

import pytest
from adaptive_postcare.agents.care_plan_agent import CarePlanAgent, StructuredCarePlan
from adaptive_postcare.state.patient_state import RiskLevel, MonitoringFrequency, PatientStateModel


@pytest.fixture
def agent() -> CarePlanAgent:
    return CarePlanAgent()


# ==============================================================================
# 1. LOW RISK TEST
# ==============================================================================

def test_care_plan_agent_low_risk(agent: CarePlanAgent):
    """
    Test LOW risk input with a variable 14-day duration.
    Verifies that care duration is assigned 14 days (NOT 30 days) and monitoring is DAILY.
    """
    plan = agent.generate_care_plan(
        patient_id="PT-LOW-01",
        risk_score=0.18,
        risk_level="LOW",
        care_duration_days=14,  # Non-30 day duration
    )

    assert isinstance(plan, StructuredCarePlan)
    assert plan.patient_id == "PT-LOW-01"
    assert plan.risk_score == 0.18
    assert plan.risk_level == "LOW"
    assert plan.total_care_duration_days == 14  # Strictly assigned
    assert plan.current_day == 0
    assert plan.monitoring_frequency == MonitoringFrequency.DAILY.value
    assert plan.daily_checkin_required is True

    # Validate symptom monitoring strategy
    assert plan.symptom_monitoring_strategy["mode"] == "LIGHT_DAILY_SELF_REPORT"
    assert "vitals_frequency_hours" in plan.symptom_monitoring_strategy

    # Validate medication monitoring strategy
    assert plan.medication_monitoring_strategy["protocol"] == "SELF_REPORTED_COMPLIANCE"
    assert plan.medication_monitoring_strategy["adherence_minimum_threshold"] == 0.70

    # Validate follow-up strategy & escalation policy
    assert "clinical_touchpoint" in plan.followup_strategy
    assert plan.escalation_policy_reference["policy_id"] == "ESC-POL-LOW-04"
    assert plan.patient_guidance_summary is not None


# ==============================================================================
# 2. MEDIUM RISK TEST
# ==============================================================================

def test_care_plan_agent_medium_risk(agent: CarePlanAgent):
    """
    Test MEDIUM risk input with a variable 21-day duration.
    Verifies that care duration is 21 days and monitoring is TWICE_DAILY.
    """
    plan = agent.generate_care_plan(
        patient_id="PT-MED-02",
        risk_score=0.52,
        risk_level="MEDIUM",
        care_duration_days=21,  # Non-30 day duration
    )

    assert plan.patient_id == "PT-MED-02"
    assert plan.risk_score == 0.52
    assert plan.risk_level == "MEDIUM"
    assert plan.total_care_duration_days == 21
    assert plan.current_day == 0
    assert plan.monitoring_frequency == MonitoringFrequency.TWICE_DAILY.value
    assert plan.daily_checkin_required is True

    # Strategy verifications
    assert plan.symptom_monitoring_strategy["mode"] == "STANDARD_DAILY_MONITORING"
    assert plan.medication_monitoring_strategy["adherence_minimum_threshold"] == 0.80
    assert plan.escalation_policy_reference["policy_id"] == "ESC-POL-MED-03"


# ==============================================================================
# 3. HIGH RISK TEST
# ==============================================================================

def test_care_plan_agent_high_risk(agent: CarePlanAgent):
    """
    Test HIGH risk input with a variable 45-day duration.
    Verifies that care duration is 45 days, frequency is HOURLY_12, and nurse touchpoints are configured.
    """
    plan = agent.generate_care_plan(
        patient_id="PT-HIGH-03",
        risk_score=0.85,
        risk_level=RiskLevel.HIGH,
        care_duration_days=45,  # Non-30 day duration
    )

    assert plan.patient_id == "PT-HIGH-03"
    assert plan.risk_score == 0.85
    assert plan.risk_level == "HIGH"
    assert plan.total_care_duration_days == 45
    assert plan.current_day == 0
    assert plan.monitoring_frequency == MonitoringFrequency.HOURLY_12.value
    assert plan.daily_checkin_required is True

    # High-risk intensive monitoring verification
    assert plan.symptom_monitoring_strategy["mode"] == "HIGH_FREQUENCY_MONITORING"
    assert "blood_pressure" in plan.symptom_monitoring_strategy["required_vitals"]
    assert plan.followup_strategy["clinical_touchpoint"] == "NURSE_PHONE_CHECKIN_48H"
    assert plan.followup_strategy["weekly_md_review"] is True
    assert plan.escalation_policy_reference["policy_id"] == "ESC-POL-HIGH-02"


# ==============================================================================
# 4. CRITICAL RISK TEST
# ==============================================================================

def test_care_plan_agent_critical_risk(agent: CarePlanAgent):
    """
    Test CRITICAL risk input with a variable 7-day duration.
    """
    plan = agent.generate_care_plan(
        patient_id="PT-CRIT-04",
        risk_score=0.96,
        risk_level="CRITICAL",
        care_duration_days=7,
    )
    assert plan.total_care_duration_days == 7
    assert plan.monitoring_frequency == MonitoringFrequency.HOURLY_6.value
    assert plan.followup_strategy["clinical_touchpoint"] == "DAILY_VIRTUAL_NURSE_ROUND"
    assert plan.escalation_policy_reference["escalation_sla_minutes"] == 15


# ==============================================================================
# 5. INPUT VALIDATION & STATE INITIALIZATION TESTS
# ==============================================================================

def test_care_plan_agent_invalid_care_duration(agent: CarePlanAgent):
    """Ensure non-positive care durations raise ValueError."""
    with pytest.raises(ValueError, match="care_duration_days must be >= 1"):
        agent.generate_care_plan(
            patient_id="PT-ERR",
            risk_score=0.5,
            risk_level="MEDIUM",
            care_duration_days=0,
        )


def test_care_plan_agent_invalid_risk_level(agent: CarePlanAgent):
    """Ensure unknown risk levels raise ValueError."""
    with pytest.raises(ValueError, match="Unknown risk_level"):
        agent.generate_care_plan(
            patient_id="PT-ERR",
            risk_score=0.5,
            risk_level="UNKNOWN_TIER",
            care_duration_days=30,
        )


def test_care_plan_agent_initialize_patient_state(agent: CarePlanAgent):
    """Ensure CarePlanAgent initializes a complete PatientStateModel with custom duration."""
    state_model = agent.initialize_patient_state(
        patient_id="PT-STATE-INIT",
        risk_score=0.72,
        risk_level="HIGH",
        care_duration_days=60,  # 60-day care duration
    )

    assert isinstance(state_model, PatientStateModel)
    assert state_model.patient_id == "PT-STATE-INIT"
    assert state_model.care_duration_days == 60
    assert state_model.current_day == 0
    assert state_model.monitoring_frequency == MonitoringFrequency.HOURLY_12
    assert state_model.care_plan["total_care_duration_days"] == 60
