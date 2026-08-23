"""
Telegram View: Presentation layer for formatting Telegram user interface messages,
clinical status cards, longitudinal history summaries, and recovery plan details.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime


class TelegramView:
    """
    Formats clinical data and agent states into clean, readable Markdown for Telegram.
    Zero business logic—pure presentation and layout.
    """

    @staticmethod
    def format_welcome_message(user_name: str, patient_id: str) -> str:
        """Formats the initial greeting and bot instructions."""
        return (
            f"👋 Hello {user_name}! I am **Nurse Elena**, your AI Post-Discharge Recovery Assistant.\n\n"
            f"I am actively monitoring your recovery for **Patient ID: `{patient_id}`** using an autonomous 7-node clinical intelligence agent.\n\n"
            f"**Available Commands:**\n"
            f"• `/status` - View current recovery metrics, risk level & next check-in\n"
            f"• `/history` - View past day-by-day longitudinal check-in records\n"
            f"• `/plan` - View post-care recovery plan details\n"
            f"• `/patient <ID>` - Switch patient profile (e.g. `/patient P005`)\n"
            f"• `/reset` - Restart check-in dialogue\n\n"
            f"💡 *How are you feeling right now? Any pain, soreness, or questions about your medications?*"
        )

    @staticmethod
    def format_patient_switch(patient_id: str) -> str:
        """Formats message when switching active patient."""
        return (
            f"✅ Switched active monitoring patient to **`{patient_id}`**.\n\n"
            f"Type `/status` to view their clinical recovery state, or `/history` for past days."
        )

    @staticmethod
    def format_status_card(
        patient_id: str,
        current_day: int,
        care_duration: int,
        plan_status: str,
        risk_level: str,
        risk_score: float,
        symptoms: List[str],
        medication_adherence: float,
        monitoring_frequency: str,
        current_action: str,
        clinical_note: str,
        next_checkin_text: str,
    ) -> str:
        """Formats comprehensive live Agentic Status Card."""
        symptoms_txt = ", ".join(symptoms) if symptoms else "None (Recovering well)"
        return (
            f"🏥 *CLINICAL AGENT STATUS: Patient {patient_id}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 *Timeline:* Day {current_day} of {care_duration} ({plan_status})\n"
            f"🛡️ *Risk Level:* `{risk_level}` (Score: {risk_score:.2f})\n"
            f"🩺 *Extracted Symptoms:* {symptoms_txt}\n"
            f"💊 *Cumulative Adherence:* {medication_adherence * 100:.0f}%\n"
            f"🔄 *Monitoring Cadence:* `{monitoring_frequency}`\n"
            f"⚡ *Latest Graph Action:* `{current_action}`\n"
            f"📋 *Clinical Decision:* {clinical_note}\n"
            f"⏰ *Next Scheduled Check-in:* {next_checkin_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 _Send any recovery update or question to trigger the next 7-node evaluation._"
        )

    @staticmethod
    def format_history_summary(
        patient_id: str,
        feedbacks: List[Any],
        actions_by_day: Dict[int, str],
    ) -> str:
        """Formats past day-by-day longitudinal check-in records."""
        if not feedbacks:
            return f"No prior history found for Patient `{patient_id}`."

        lines = [
            f"📜 *LONGITUDINAL HISTORY: Patient {patient_id}*",
            "━━━━━━━━━━━━━━━━━━━━━━"
        ]
        for fb in feedbacks:
            symps = fb.structured_feedback.get("extracted_symptoms", [])
            symp_str = ", ".join(symps) if symps else "No symptoms (Stable)"
            med_str = "Taken ✅" if fb.structured_feedback.get("medication_taken") else "Missed ⚠️"
            act_str = actions_by_day.get(fb.day, "CONTINUE")
            lines.append(f"• *Day {fb.day}:* Symptoms: _{symp_str}_ | Meds: {med_str} | Action: `{act_str}`")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    @staticmethod
    def format_care_plan(
        patient_id: str,
        patient_name: str,
        diagnosis: str,
        status: str,
        duration_days: int,
        current_day: int,
        monitoring_frequency: str,
        risk_level: str,
        risk_score: float,
        prescribed_medications: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Formats care plan details."""
        lines = [
            f"📋 *CARE PLAN DETAILS: Patient {patient_id} ({patient_name})*",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"• *Primary Diagnosis:* {diagnosis}",
            f"• *Plan Status:* {status}",
            f"• *Assigned Duration:* {duration_days} days (Current: Day {current_day})",
            f"• *Monitoring Frequency:* {monitoring_frequency}",
            f"• *Baseline Risk Tier:* {risk_level} ({risk_score:.2f})",
        ]
        if prescribed_medications:
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("💊 *Prescribed Discharge Medications:*")
            for m in prescribed_medications:
                lines.append(f"  • *{m.get('name')}* ({m.get('dose')}): _{m.get('frequency')}_")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    @staticmethod
    def format_daily_care_summary(
        patient_id: str,
        patient_name: str,
        current_day: int,
        diagnosis: str,
        prescribed_medications: List[Dict[str, Any]],
        nutrition_guidelines: str,
        activity_target: str,
        wound_care: str,
        next_checkin_text: str,
    ) -> str:
        """Formats comprehensive Day Care Plan Card at the end of a check-in."""
        med_lines = []
        for m in prescribed_medications:
            med_lines.append(f"  • *{m.get('name')}* ({m.get('dose')}): _{m.get('frequency')}_")
        meds_block = "\n".join(med_lines) if med_lines else "  • Take medications as prescribed by your surgeon."

        return (
            f"🌟 *DAY {current_day} RECOVERY CARE PLAN: {patient_name}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏥 *Condition:* {diagnosis}\n\n"
            f"💊 *Today's Medication Schedule:*\n"
            f"{meds_block}\n\n"
            f"🥗 *Nutrition & Hydration:*\n"
            f"  • {nutrition_guidelines}\n\n"
            f"🚶 *Mobility & Activity Target:*\n"
            f"  • {activity_target}\n\n"
            f"🛡️ *Care & Comfort Tip:*\n"
            f"  • {wound_care}\n\n"
            f"⏰ *Next Check-in:* {next_checkin_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💚 _Rest well today! You can message me anytime if you feel any new symptoms or need help._"
        )

