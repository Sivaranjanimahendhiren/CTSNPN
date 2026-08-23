"""
Adaptation Policies: Evaluates trajectory comparisons between current state and historical records.
Enforces deterministic decision policies across all eight clinical post-care scenarios.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from ..state.patient_state import PatientState, CareAction, PlanStatus, DataQuality, MonitoringFrequency


class AdaptationDecision(BaseModel):
    """Result of adaptive trajectory evaluation."""
    scenario_id: str = Field(..., description="SCENARIO_1 through SCENARIO_8 identifier")
    selected_action: str = Field(..., description="Action: CONTINUE, INCREASE_MONITORING, DECREASE_MONITORING, etc.")
    target_frequency: Optional[str] = Field(default=None, description="Adjusted monitoring cadence if changed")
    plan_status: str = Field(default=PlanStatus.ACTIVE.value)
    reason: str = Field(..., description="Clinical / operational rationale for adaptation")


def evaluate_adaptive_trajectory(state: PatientState) -> AdaptationDecision:
    """
    Compares current patient state with history across the 8 clinical scenarios.
    """
    current_day = state.get("current_day", 0)
    care_duration = state.get("care_duration_days", 30)
    escalation_required = state.get("escalation_required", False)
    data_quality = state.get("data_quality", DataQuality.GOOD.value)
    current_freq = state.get("monitoring_frequency", MonitoringFrequency.DAILY.value)
    adherence = state.get("medication_adherence", 1.0)
    symptoms = state.get("symptoms", [])
    risk_level = str(state.get("risk_level", "LOW")).upper()
    current_event = state.get("current_event")

    # --------------------------------------------------------------------------
    # SCENARIO 8: Care window reached (current_day >= care_duration_days)
    # --------------------------------------------------------------------------
    if current_day >= care_duration and not escalation_required:
        return AdaptationDecision(
            scenario_id="SCENARIO_8_COMPLETE",
            selected_action=CareAction.COMPLETE.value,
            target_frequency=current_freq,
            plan_status=PlanStatus.COMPLETED.value,
            reason=f"Patient completed designated care monitoring duration of {care_duration} days."
        )

    # --------------------------------------------------------------------------
    # SCENARIO 7: Configured escalation criteria satisfied
    # --------------------------------------------------------------------------
    if escalation_required:
        return AdaptationDecision(
            scenario_id="SCENARIO_7_ESCALATION",
            selected_action=CareAction.ESCALATE.value,
            target_frequency=MonitoringFrequency.HOURLY_6.value,
            plan_status=PlanStatus.ESCALATED.value,
            reason="Clinical escalation criteria met. Triggering clinician alert."
        )

    # --------------------------------------------------------------------------
    # SCENARIO 5: Patient does not respond (No check-in / missing data)
    # --------------------------------------------------------------------------
    if data_quality == DataQuality.INCOMPLETE.value or (current_event is not None and not current_event.get("feedback") and data_quality != DataQuality.GOOD.value):
        return AdaptationDecision(
            scenario_id="SCENARIO_5_NO_RESPONSE",
            selected_action=CareAction.REQUEST_MORE_DATA.value,
            target_frequency=current_freq,
            plan_status=PlanStatus.ACTIVE.value,
            reason="No patient response received. Requesting check-in data (patient cannot be assumed healthy)."
        )

    # --------------------------------------------------------------------------
    # SCENARIO 6: Inconsistent / degraded data
    # --------------------------------------------------------------------------
    if data_quality in [DataQuality.POOR.value, DataQuality.DEGRADED.value]:
        return AdaptationDecision(
            scenario_id="SCENARIO_6_INCONSISTENT_DATA",
            selected_action=CareAction.REQUEST_MORE_DATA.value,
            target_frequency=current_freq,
            plan_status=PlanStatus.ACTIVE.value,
            reason="Inconsistent or incomplete telemetry detected. Requesting data clarification."
        )

    # --------------------------------------------------------------------------
    # SCENARIO 4: Medication adherence decreases
    # --------------------------------------------------------------------------
    if adherence < 0.80:
        return AdaptationDecision(
            scenario_id="SCENARIO_4_ADHERENCE_DECREASE",
            selected_action=CareAction.MODIFY_CARE_PLAN.value,
            target_frequency=current_freq,
            plan_status=PlanStatus.ACTIVE.value,
            reason=f"Medication adherence dropped to {adherence * 100:.0f}%. Initiating adherence support."
        )

    # --------------------------------------------------------------------------
    # SCENARIO 3: Patient condition is worsening (active/new symptoms)
    # --------------------------------------------------------------------------
    if len(symptoms) > 0:
        step_up_map = {
            MonitoringFrequency.WEEKLY.value: MonitoringFrequency.DAILY.value,
            MonitoringFrequency.DAILY.value: MonitoringFrequency.TWICE_DAILY.value,
            MonitoringFrequency.TWICE_DAILY.value: MonitoringFrequency.HOURLY_12.value,
            MonitoringFrequency.HOURLY_12.value: MonitoringFrequency.HOURLY_6.value,
            MonitoringFrequency.HOURLY_6.value: MonitoringFrequency.HOURLY_6.value,
        }
        new_freq = step_up_map.get(current_freq, MonitoringFrequency.TWICE_DAILY.value)
        return AdaptationDecision(
            scenario_id="SCENARIO_3_WORSENING",
            selected_action=CareAction.INCREASE_MONITORING.value,
            target_frequency=new_freq,
            plan_status=PlanStatus.ACTIVE.value,
            reason=f"Active symptoms detected ({', '.join(symptoms)}). Stepping up monitoring cadence to {new_freq}."
        )

    # --------------------------------------------------------------------------
    # SCENARIO 2: Patient is improving consistently (on elevated monitoring)
    # --------------------------------------------------------------------------
    if not symptoms and adherence >= 0.95:
        if current_freq == MonitoringFrequency.HOURLY_6.value:
            return AdaptationDecision(
                scenario_id="SCENARIO_2_IMPROVING",
                selected_action=CareAction.DECREASE_MONITORING.value,
                target_frequency=MonitoringFrequency.HOURLY_12.value,
                plan_status=PlanStatus.ACTIVE.value,
                reason="Patient consistently improving with symptoms resolved. Stepping down monitoring to HOURLY_12."
            )
        elif current_freq == MonitoringFrequency.HOURLY_12.value and risk_level in ["LOW", "MEDIUM"]:
            return AdaptationDecision(
                scenario_id="SCENARIO_2_IMPROVING",
                selected_action=CareAction.DECREASE_MONITORING.value,
                target_frequency=MonitoringFrequency.TWICE_DAILY.value,
                plan_status=PlanStatus.ACTIVE.value,
                reason="Patient consistently improving with symptoms resolved. Stepping down monitoring to TWICE_DAILY."
            )

    # --------------------------------------------------------------------------
    # SCENARIO 1: Patient is stable
    # --------------------------------------------------------------------------
    return AdaptationDecision(
        scenario_id="SCENARIO_1_STABLE",
        selected_action=CareAction.CONTINUE.value,
        target_frequency=current_freq,
        plan_status=PlanStatus.ACTIVE.value,
        reason="Patient condition stable, adherent, and within baseline thresholds. Continuing routine plan."
    )
