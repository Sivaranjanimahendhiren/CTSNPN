"""
Execution Tracer for Adaptive Post-Care System.
Formats clear, human-readable execution traces demonstrating node-by-node transitions,
state mutations, policy decisions, and conditional routing.
"""

from typing import Any, Dict, List, Optional
from ..state.patient_state import PatientState


class ExecutionTracer:
    """
    Captures and renders step-by-step execution traces for post-care patient journeys.
    """

    @staticmethod
    def format_step_trace(
        patient_id: str,
        risk_level: str,
        care_duration_days: int,
        current_day: int,
        node_name: str,
        state_change: str,
        decision: str,
        next_node: str,
        final_action: str,
    ) -> str:
        """
        Renders a single step trace block conforming to the visual specification.
        """
        return f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PATIENT EXECUTION TRACE                                                      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ Patient ID     : {patient_id:<58} ║
║ Risk Level     : {risk_level:<58} ║
║ Care Duration  : {f"{care_duration_days} days":<58} ║
║ Current Day    : {f"Day {current_day} of {care_duration_days}":<58} ║
║ Node Executed  : {node_name:<58} ║
║ State Change   : {state_change:<58} ║
║ Decision       : {decision:<58} ║
║ Next Node      : {next_node:<58} ║
║ Final Action   : {final_action:<58} ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

    @staticmethod
    def print_journey_summary(patient_id: str, final_state: Dict[str, Any], scenario_name: str):
        """
        Prints a structured summary of the patient's updated state and action trail.
        """
        freq = final_state.get("monitoring_frequency", "DAILY")
        status = final_state.get("plan_status", "ACTIVE")
        action = final_state.get("current_action", "NONE")
        symptoms = final_state.get("symptoms", [])
        adherence = final_state.get("medication_adherence", 1.0)
        quality = final_state.get("data_quality", "GOOD")
        notes = final_state.get("adaptation_notes", [])
        latest_note = notes[-1] if notes else "No adaptation notes"

        print(f"\n================================================================================")
        print(f" SCENARIO: {scenario_name}")
        print(f" Patient ID        : {patient_id}")
        print(f" Status            : {status}")
        print(f" Final Action      : {action}")
        print(f" Monitoring Cadence: {freq}")
        print(f" Active Symptoms   : {', '.join(symptoms) if symptoms else 'None'}")
        print(f" Adherence Rate    : {adherence * 100:.0f}%")
        print(f" Data Quality      : {quality}")
        print(f" Latest Note       : {latest_note}")
        print(f"================================================================================\n")
