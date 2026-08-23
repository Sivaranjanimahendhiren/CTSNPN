"""
Tools package for the Adaptive Agentic Post-Care System.
Provides 7 specialized LangChain tools with strongly typed Pydantic input and output schemas.
"""

from .patient_state_tool import patient_state_tool, PatientStateInput, PatientStateOutput
from .care_plan_tool import care_plan_tool, CarePlanInput, CarePlanOutput
from .notification_tool import checkin_notification_tool, CheckinNotificationInput, CheckinNotificationOutput
from .medication_tool import medication_adherence_tool, MedicationInput, MedicationOutput
from .monitoring_tool import monitoring_cadence_tool, MonitoringInput, MonitoringOutput
from .appointment_tool import appointment_scheduling_tool, AppointmentInput, AppointmentOutput
from .escalation_tool import clinical_escalation_tool, EscalationInput, EscalationOutput

# Backwards compatibility aliases
from .alert_tools import alert_care_team, alert_emergency_services
from .care_tools import send_patient_notification, schedule_followup, log_intervention

ALL_AGENT_TOOLS = [
    patient_state_tool,
    care_plan_tool,
    checkin_notification_tool,
    medication_adherence_tool,
    monitoring_cadence_tool,
    appointment_scheduling_tool,
    clinical_escalation_tool,
]

__all__ = [
    # 7 Core Tools
    "patient_state_tool",
    "care_plan_tool",
    "checkin_notification_tool",
    "medication_adherence_tool",
    "monitoring_cadence_tool",
    "appointment_scheduling_tool",
    "clinical_escalation_tool",
    "ALL_AGENT_TOOLS",
    # Input/Output Schemas
    "PatientStateInput",
    "PatientStateOutput",
    "CarePlanInput",
    "CarePlanOutput",
    "CheckinNotificationInput",
    "CheckinNotificationOutput",
    "MedicationInput",
    "MedicationOutput",
    "MonitoringInput",
    "MonitoringOutput",
    "AppointmentInput",
    "AppointmentOutput",
    "EscalationInput",
    "EscalationOutput",
    # Aliases
    "alert_care_team",
    "alert_emergency_services",
    "send_patient_notification",
    "schedule_followup",
    "log_intervention",
]
