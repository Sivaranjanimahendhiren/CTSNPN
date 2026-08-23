"""
Clinical care protocols and guidelines based on risk tiers.
Enforces explicit, deterministic medical thresholds and operational strategies.
"""

from typing import Dict, Any, List
from pydantic import BaseModel, Field
from ..state.patient_state import MonitoringFrequency


class CarePolicyConfig(BaseModel):
    """
    Structured policy specification defining deterministic parameters for a risk tier.
    No LLM is permitted to invent or alter these clinical thresholds.
    """
    risk_level: str
    monitoring_frequency: str = Field(..., description="Monitoring cadence: HOURLY_6, HOURLY_12, TWICE_DAILY, DAILY")
    check_in_frequency_hours: int = Field(..., description="Proactive check-in interval in hours")
    daily_checkin_required: bool = Field(default=True, description="Whether at least one check-in per day is mandatory")
    symptom_monitoring_strategy: Dict[str, Any] = Field(..., description="Explicit symptom tracking regimen")
    medication_monitoring_strategy: Dict[str, Any] = Field(..., description="Medication adherence tracking protocol")
    followup_strategy: Dict[str, Any] = Field(..., description="Clinical team review and followup schedule")
    escalation_policy_reference: Dict[str, Any] = Field(..., description="Deterministic escalation thresholds and contacts")
    requires_nurse_review: bool = Field(default=False)
    mandatory_escalation_symptoms: List[str] = Field(default_factory=list)


# Configurable risk policy registry
RISK_POLICIES: Dict[str, CarePolicyConfig] = {
    "CRITICAL": CarePolicyConfig(
        risk_level="CRITICAL",
        monitoring_frequency=MonitoringFrequency.HOURLY_6.value,
        check_in_frequency_hours=6,
        daily_checkin_required=True,
        symptom_monitoring_strategy={
            "mode": "CONTINUOUS_INTENSIVE",
            "required_vitals": ["blood_pressure", "heart_rate", "oxygen_saturation", "temperature"],
            "vitals_frequency_hours": 6,
            "symptom_survey_interval_hours": 6,
        },
        medication_monitoring_strategy={
            "protocol": "EVERY_DOSE_CONFIRMATION",
            "missed_dose_alert_threshold": 1,
            "adherence_minimum_threshold": 0.95,
        },
        followup_strategy={
            "clinical_touchpoint": "DAILY_VIRTUAL_NURSE_ROUND",
            "first_clinician_call_within_hours": 12,
            "weekly_md_review": True,
        },
        escalation_policy_reference={
            "policy_id": "ESC-POL-CRITICAL-01",
            "tier": "CRITICAL",
            "emergency_symptoms": ["chest pain", "shortness of breath", "loss of consciousness", "fever > 103", "hemorrhage"],
            "escalation_sla_minutes": 15,
            "target": "ON_CALL_PULMONOLOGIST_OR_CARDIOLOGY_TEAM",
        },
        requires_nurse_review=True,
        mandatory_escalation_symptoms=["chest pain", "shortness of breath", "fainting", "fever > 103"],
    ),
    "HIGH": CarePolicyConfig(
        risk_level="HIGH",
        monitoring_frequency=MonitoringFrequency.HOURLY_12.value,
        check_in_frequency_hours=12,
        daily_checkin_required=True,
        symptom_monitoring_strategy={
            "mode": "HIGH_FREQUENCY_MONITORING",
            "required_vitals": ["blood_pressure", "heart_rate", "temperature"],
            "vitals_frequency_hours": 12,
            "symptom_survey_interval_hours": 12,
        },
        medication_monitoring_strategy={
            "protocol": "TWICE_DAILY_CONFIRMATION",
            "missed_dose_alert_threshold": 1,
            "adherence_minimum_threshold": 0.90,
        },
        followup_strategy={
            "clinical_touchpoint": "NURSE_PHONE_CHECKIN_48H",
            "first_clinician_call_within_hours": 24,
            "weekly_md_review": True,
        },
        escalation_policy_reference={
            "policy_id": "ESC-POL-HIGH-02",
            "tier": "HIGH",
            "emergency_symptoms": ["chest pain", "severe dyspnea", "persistent high fever", "acute swelling"],
            "escalation_sla_minutes": 30,
            "target": "PRIMARY_CARE_NURSE_COORDINATOR",
        },
        requires_nurse_review=True,
        mandatory_escalation_symptoms=["chest pain", "severe dyspnea", "persistent high fever"],
    ),
    "MEDIUM": CarePolicyConfig(
        risk_level="MEDIUM",
        monitoring_frequency=MonitoringFrequency.TWICE_DAILY.value,
        check_in_frequency_hours=24,
        daily_checkin_required=True,
        symptom_monitoring_strategy={
            "mode": "STANDARD_DAILY_MONITORING",
            "required_vitals": ["blood_pressure", "weight"],
            "vitals_frequency_hours": 24,
            "symptom_survey_interval_hours": 24,
        },
        medication_monitoring_strategy={
            "protocol": "DAILY_MEDICATION_LOG",
            "missed_dose_alert_threshold": 2,
            "adherence_minimum_threshold": 0.80,
        },
        followup_strategy={
            "clinical_touchpoint": "DAY_7_TELEHEALTH_VISIT",
            "first_clinician_call_within_hours": 72,
            "weekly_md_review": False,
        },
        escalation_policy_reference={
            "policy_id": "ESC-POL-MED-03",
            "tier": "MEDIUM",
            "emergency_symptoms": ["chest pain", "acute distress", "uncontrolled hypertension"],
            "escalation_sla_minutes": 60,
            "target": "TELEHEALTH_TRIAGE_POOL",
        },
        requires_nurse_review=False,
        mandatory_escalation_symptoms=["chest pain", "acute distress"],
    ),
    "LOW": CarePolicyConfig(
        risk_level="LOW",
        monitoring_frequency=MonitoringFrequency.DAILY.value,
        check_in_frequency_hours=24,
        daily_checkin_required=True,
        symptom_monitoring_strategy={
            "mode": "LIGHT_DAILY_SELF_REPORT",
            "required_vitals": ["self_reported_wellness"],
            "vitals_frequency_hours": 48,
            "symptom_survey_interval_hours": 24,
        },
        medication_monitoring_strategy={
            "protocol": "SELF_REPORTED_COMPLIANCE",
            "missed_dose_alert_threshold": 3,
            "adherence_minimum_threshold": 0.70,
        },
        followup_strategy={
            "clinical_touchpoint": "POST_DISCHARGE_DAY_14_SURVEY",
            "first_clinician_call_within_hours": 168,  # 7 days
            "weekly_md_review": False,
        },
        escalation_policy_reference={
            "policy_id": "ESC-POL-LOW-04",
            "tier": "LOW",
            "emergency_symptoms": ["chest pain", "loss of consciousness"],
            "escalation_sla_minutes": 120,
            "target": "CARE_PORTAL_MESSAGING",
        },
        requires_nurse_review=False,
        mandatory_escalation_symptoms=["chest pain", "loss of consciousness"],
    ),
}


def get_default_policy_for_risk(risk_level: str) -> CarePolicyConfig:
    """
    Returns the deterministic clinical policy configuration for a given risk level.
    """
    cleaned = risk_level.strip().upper()
    if cleaned not in RISK_POLICIES:
        raise ValueError(f"Unknown risk_level '{risk_level}'. Valid options: {list(RISK_POLICIES.keys())}")
    return RISK_POLICIES[cleaned]
