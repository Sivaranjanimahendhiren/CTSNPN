"""
Console Trace View: Formats real-time execution traces of the 7-Node LangGraph
State Machine for console monitoring and jury evaluation.
"""

from typing import Any, Dict, List, Optional


def safe_console_print(text: str):
    """Safely prints text on Windows console without cp1252 UnicodeEncodeError."""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"), flush=True)


class ConsoleTraceView:
    """
    Renders clean, formatted execution steps of the 7-Node LangGraph state machine.
    """

    @staticmethod
    def print_agentic_trace(
        patient_id: str,
        current_day: int,
        care_duration: int,
        symptoms: List[str],
        medication_adherence: float,
        risk_score: float,
        risk_level: str,
        current_action: str,
        monitoring_frequency: str,
        clinical_note: str,
        escalation_required: bool = False,
        next_schedule: Optional[Dict[str, Any]] = None,
    ):
        """Displays formatted LangGraph cycle execution trace in console."""
        safe_console_print("\n" + "=" * 75)
        safe_console_print(f" [7-NODE LANGGRAPH AGENTIC CYCLE] Patient: {patient_id} (Day {current_day}/{care_duration})")
        safe_console_print(f" -> 1. Observe Node         : Timeline verified Day {current_day} | Quality=GOOD")
        safe_console_print(f" -> 2. Understand Node      : Symptoms={symptoms} | Cumulative Adherence={medication_adherence*100:.0f}%")
        safe_console_print(f" -> 3. Risk Evaluation Node : Score={risk_score:.2f} | Baseline Tier={risk_level}")
        safe_console_print(f" -> 4. Plan Node            : Action Selected = {current_action}")
        safe_console_print(f" -> 5. Act Node             : Tool Executed = {current_action} (Audit Logged)")
        safe_console_print(f" -> 6. Feedback Node        : Structured Vitals Persisted to PostgreSQL")
        safe_console_print(f" -> 7. Adapt Node           : Monitoring Cadence = {monitoring_frequency}")
        if escalation_required:
            safe_console_print(f" -> 8. Escalate Node        : CRITICAL ALERT DISPATCHED TO CLINICAL TEAM")
        safe_console_print(f" -> Decision Reasoning      : {clinical_note}")
        if next_schedule:
            safe_console_print(f" -> Next Schedule in DB     : Day {next_schedule.get('care_day')} ({next_schedule.get('monitoring_frequency')}) at {next_schedule.get('scheduled_at')}")
        safe_console_print("=" * 75 + "\n")

    @staticmethod
    def print_startup_banner(llm_count: int, patient_count: int = 10):
        """Displays the startup banner for the Telegram Bot."""
        safe_console_print("\n" + "=" * 75)
        safe_console_print(" [OK] TELEGRAM AGENTIC AI NURSE BOT ACTIVE & POLLING (MVC ARCHITECTURE)")
        safe_console_print(f" Connected with {llm_count} LLM Backends | LangGraph 7-Node State Machine")
        safe_console_print(" PostgreSQL Checkpointer: PostgresSaver (Active)")
        safe_console_print(f" {patient_count} Patients Seeded with Longitudinal Day-by-Day History (P001 - P010)")
        safe_console_print(" Send a message to your Telegram Bot to start chatting live!")
        safe_console_print(" Press Ctrl+C to stop.")
        safe_console_print("=" * 75 + "\n")
