"""
Comprehensive unit tests for the seven agent tools:
1. Patient State Tool
2. Care Plan Tool
3. Check-in / Notification Tool
4. Medication Tool
5. Monitoring Tool
6. Appointment Tool
7. Escalation Tool
"""

import pytest
from adaptive_postcare.tools import (
    patient_state_tool,
    care_plan_tool,
    checkin_notification_tool,
    medication_adherence_tool,
    monitoring_cadence_tool,
    appointment_scheduling_tool,
    clinical_escalation_tool,
    PatientStateInput,
    CarePlanInput,
    CheckinNotificationInput,
    MedicationInput,
    MonitoringInput,
    AppointmentInput,
    EscalationInput,
)


# ==============================================================================
# 1. PATIENT STATE TOOL TESTS
# ==============================================================================

def test_patient_state_tool_get_and_update():
    patient_id = "PT-STATE-001"

    # Initial GET
    get_res = patient_state_tool.invoke({"patient_id": patient_id, "action": "GET"})
    assert get_res["status"] == "SUCCESS"
    assert get_res["patient_id"] == patient_id
    assert get_res["action_performed"] == "GET"

    # UPDATE
    update_res = patient_state_tool.invoke({
        "patient_id": patient_id,
        "action": "UPDATE",
        "state_updates": {"current_day": 3, "symptoms": ["mild dizziness"]}
    })
    assert update_res["status"] == "SUCCESS"
    assert update_res["action_performed"] == "UPDATE"
    assert update_res["state_data"]["current_day"] == 3
    assert "mild dizziness" in update_res["state_data"]["symptoms"]


# ==============================================================================
# 2. CARE PLAN TOOL TESTS
# ==============================================================================

def test_care_plan_tool_get_and_modify():
    patient_id = "PT-PLAN-002"

    # GET default
    get_res = care_plan_tool.invoke({"patient_id": patient_id, "action": "GET"})
    assert get_res["status"] == "SUCCESS"

    # MODIFY plan
    mod_res = care_plan_tool.invoke({
        "patient_id": patient_id,
        "action": "MODIFY",
        "plan_data": {"monitoring_frequency": "TWICE_DAILY", "adherence_support_active": True}
    })
    assert mod_res["status"] == "SUCCESS"
    assert mod_res["care_plan"]["monitoring_frequency"] == "TWICE_DAILY"
    assert mod_res["care_plan"]["adherence_support_active"] is True


# ==============================================================================
# 3. CHECK-IN / NOTIFICATION TOOL TESTS
# ==============================================================================

def test_checkin_notification_tool():
    res = checkin_notification_tool.invoke({
        "patient_id": "PT-NOTIF-003",
        "day": 5,
        "message": "Time for your daily vitals check-in. Please log blood pressure.",
        "channel": "SMS"
    })
    assert res["status"] == "DELIVERED"
    assert res["patient_id"] == "PT-NOTIF-003"
    assert res["day"] == 5
    assert res["channel"] == "SMS"
    assert "NOTIF-PT-NOTIF-003-5" in res["notification_id"]
    assert "timestamp" in res


# ==============================================================================
# 4. MEDICATION TOOL TESTS
# ==============================================================================

def test_medication_tool_compliance_and_missed_dose():
    patient_id = "PT-MED-004"

    # Log 1: Dose taken
    res1 = medication_adherence_tool.invoke({
        "patient_id": patient_id,
        "medication_taken": True,
        "day": 1,
    })
    assert res1["updated_adherence"] == 1.0
    assert res1["consecutive_missed_doses"] == 0
    assert res1["requires_adherence_counseling"] is False

    # Log 2: Dose missed
    res2 = medication_adherence_tool.invoke({
        "patient_id": patient_id,
        "medication_taken": False,
        "day": 2,
        "missed_reason": "Nausea / upset stomach"
    })
    assert res2["updated_adherence"] == 0.5
    assert res2["consecutive_missed_doses"] == 1
    assert res2["requires_adherence_counseling"] is True


# ==============================================================================
# 5. MONITORING TOOL TESTS
# ==============================================================================

def test_monitoring_cadence_tool_normal_and_abnormal():
    patient_id = "PT-MON-005"

    # Normal vitals
    res_normal = monitoring_cadence_tool.invoke({
        "patient_id": patient_id,
        "day": 3,
        "vitals_data": {"systolic": 120, "spo2": 98, "temp": 98.6}
    })
    assert res_normal["abnormal_vitals_detected"] is False
    assert res_normal["status"] == "RECORDED"

    # Hypertensive crisis / abnormal vitals
    res_abnormal = monitoring_cadence_tool.invoke({
        "patient_id": patient_id,
        "day": 4,
        "vitals_data": {"systolic": 175, "spo2": 90, "temp": 102.1}
    })
    assert res_abnormal["abnormal_vitals_detected"] is True
    assert "systolic" in res_abnormal["abnormal_readings"]
    assert "spo2" in res_abnormal["abnormal_readings"]
    assert "temperature" in res_abnormal["abnormal_readings"]
    assert res_abnormal["active_monitoring_frequency"] == "HOURLY_6"


# ==============================================================================
# 6. APPOINTMENT TOOL TESTS
# ==============================================================================

def test_appointment_scheduling_tool():
    res = appointment_scheduling_tool.invoke({
        "patient_id": "PT-APT-006",
        "due_in_hours": 48,
        "purpose": "Post-discharge 48-hour nurse telehealth assessment",
        "appointment_type": "NURSE_PHONE_CHECKIN"
    })
    assert res["status"] == "CONFIRMED"
    assert res["patient_id"] == "PT-APT-006"
    assert res["due_in_hours"] == 48
    assert res["appointment_type"] == "NURSE_PHONE_CHECKIN"
    assert "APT-PT-APT-006" in res["appointment_id"]


# ==============================================================================
# 7. ESCALATION TOOL TESTS
# ==============================================================================

def test_clinical_escalation_tool_emergency_and_high():
    patient_id = "PT-ESC-007"

    # Emergency escalation
    res_em = clinical_escalation_tool.invoke({
        "patient_id": patient_id,
        "reason": "Chest pain and dyspnea reported",
        "priority": "EMERGENCY",
        "symptoms": ["chest pain", "shortness of breath"]
    })
    assert res_em["status"] == "DISPATCHED"
    assert res_em["priority"] == "EMERGENCY"
    assert res_em["target_team"] == "EMERGENCY_RAPID_RESPONSE_TEAM"
    assert res_em["sla_response_minutes"] == 15

    # High priority escalation
    res_high = clinical_escalation_tool.invoke({
        "patient_id": patient_id,
        "reason": "Repeated missed medication with elevated BP",
        "priority": "HIGH"
    })
    assert res_high["priority"] == "HIGH"
    assert res_high["target_team"] == "ON_CALL_CARE_COORDINATOR"
    assert res_high["sla_response_minutes"] == 30
