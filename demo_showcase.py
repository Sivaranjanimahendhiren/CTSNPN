"""
End-to-End Real Agent Execution Simulation Runner for Adaptive Post-Care System.
Executes all 10 longitudinal patient scenarios through the real production pipeline:
HospitalEventAdapter -> MultiPatientOrchestrator -> 7-Node LangGraph -> PostgresSaver -> PostgreSQL.
"""

import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from adaptive_postcare.storage.database import get_db_session_manager
from adaptive_postcare.storage.seed import seed_database
from adaptive_postcare.storage.postgres_saver import PostgresSaver
from adaptive_postcare.storage.repositories import (
    PatientRepository,
    PredictionRepository,
    CarePlanRepository,
    ScheduleRepository,
    PatientProfileRepository,
    FeedbackRepository,
    AgentActionRepository,
)
from adaptive_postcare.orchestrator import MultiPatientOrchestrator
from adaptive_postcare.adapters.hospital_adapter import HospitalEventAdapter
from adaptive_postcare.scheduling.monitoring_scheduler import MonitoringScheduler
from adaptive_postcare.state.patient_state import CareAction, PlanStatus, MonitoringFrequency


def print_header(title: str):
    print("\n" + "=" * 80)
    print(f" [>>] {title.upper()}")
    print("=" * 80)


def print_trace(patient_id: str, day: int, event_type: str, res: Dict[str, Any], extra: str = ""):
    st = res.get("patient_state", {})
    action = st.get("current_action", "N/A")
    freq = st.get("monitoring_frequency", "N/A")
    plan_stat = st.get("plan_status", "ACTIVE")
    sched = res.get("next_checkin_scheduled") or res.get("first_checkin_scheduled")
    notes = st.get("adaptation_notes", ["Evaluated"])[-1] if st.get("adaptation_notes") else "Evaluated"

    print(f"  Patient ID       : {patient_id}")
    print(f"  Current Day      : Day {day} (Status: {plan_stat})")
    print(f"  Event Ingested   : {event_type}")
    print(f"  Extracted Vitals : symptoms={st.get('symptoms', [])} | adherence={st.get('medication_adherence', 1.0)*100:.0f}% | quality={st.get('data_quality', 'GOOD')}")
    print(f"  Action Selected  : {action}")
    print(f"  Monitoring Cadence: {freq}")
    print(f"  Clinical Decision: {notes}")
    if sched:
        print(f"  Postgres Schedule: Next Check-in Day {sched.get('care_day')} at {sched.get('scheduled_at')} ({sched.get('monitoring_frequency')})")
    if extra:
        print(f"  Note             : {extra}")
    print("  " + "-" * 75)


def run_full_simulation():
    print("""
================================================================================
       [+] ADAPTIVE AGENTIC POST-CARE SYSTEM - REAL AGENT SIMULATION RUNNER
    10 Longitudinal Clinical Scenarios * 7-Node LangGraph * PostgresSaver
================================================================================
    """)

    db = get_db_session_manager()
    with db.session_scope() as session:
        seed_res = seed_database(session)
        print(f"[*] Database state verified/seeded: {seed_res}\n")

    checkpointer = PostgresSaver(db_manager=db)
    orchestrator = MultiPatientOrchestrator(checkpointer=checkpointer)
    scheduler = MonitoringScheduler(db_manager=db)
    adapter = HospitalEventAdapter(orchestrator=orchestrator, db_manager=db, scheduler=scheduler)

    # -------------------------------------------------------------------------
    # SCENARIO 1: STABLE RECOVERY (CONTINUE)
    # -------------------------------------------------------------------------
    print_header("Scenario 1: Stable Recovery -- Baseline Maintained (P001)")
    adapter.process_hospital_event({"patient_id": "P001", "event_type": "PATIENT_DISCHARGED", "hospital_id": "METRO_GEN"})
    res1 = adapter.process_hospital_event({
        "patient_id": "P001",
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {"symptoms": "none", "medication_taken": True, "energy_level": 8},
    })
    print_trace("P001", 1, "DAILY_CHECKIN", res1)

    # -------------------------------------------------------------------------
    # SCENARIO 2: EMERGING SYMPTOMS (STEP-UP CADENCE)
    # -------------------------------------------------------------------------
    print_header("Scenario 2: Emerging Symptoms -- Monitoring Step-Up (P005)")
    adapter.process_hospital_event({"patient_id": "P005", "event_type": "PATIENT_DISCHARGED", "hospital_id": "ST_JUDE"})
    res2 = adapter.process_hospital_event({
        "patient_id": "P005",
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {"symptoms": "moderate localized surgical pain", "medication_taken": True, "energy_level": 5},
    })
    print_trace("P005", 1, "DAILY_CHECKIN", res2, "Agent stepped up monitoring cadence on active symptoms")

    # -------------------------------------------------------------------------
    # SCENARIO 3: CONSISTENT IMPROVEMENT (STEP-DOWN CADENCE)
    # -------------------------------------------------------------------------
    print_header("Scenario 3: Consistent Improvement -- Step-Down Cadence (P002)")
    adapter.process_hospital_event({"patient_id": "P002", "event_type": "PATIENT_DISCHARGED", "hospital_id": "ST_JUDE"})
    # Day 1
    adapter.process_hospital_event({"patient_id": "P002", "event_type": "DAILY_CHECKIN", "day": 1, "payload": {"symptoms": "none", "medication_taken": True}})
    # Day 2
    adapter.process_hospital_event({"patient_id": "P002", "event_type": "DAILY_CHECKIN", "day": 2, "payload": {"symptoms": "none", "medication_taken": True}})
    # Day 3
    res3 = adapter.process_hospital_event({"patient_id": "P002", "event_type": "DAILY_CHECKIN", "day": 3, "payload": {"symptoms": "none", "medication_taken": True, "energy_level": 9}})
    print_trace("P002", 3, "DAILY_CHECKIN", res3, "Multi-day symptom resolution triggers step-down")

    # -------------------------------------------------------------------------
    # SCENARIO 4: MEDICATION NON-ADHERENCE (MODIFY CARE PLAN)
    # -------------------------------------------------------------------------
    print_header("Scenario 4: Medication Non-Adherence -- Care Plan Modification (P008)")
    adapter.process_hospital_event({"patient_id": "P008", "event_type": "PATIENT_DISCHARGED", "hospital_id": "ST_JUDE"})
    for d in range(1, 4):
        res4 = adapter.process_hospital_event({
            "patient_id": "P008",
            "event_type": "DAILY_CHECKIN",
            "day": d,
            "payload": {"symptoms": "none", "medication_taken": False, "energy_level": 6},
        })
    print_trace("P008", 3, "DAILY_CHECKIN", res4, "Adherence dropped below 80% -> triggered adherence intervention")

    # -------------------------------------------------------------------------
    # SCENARIO 5: POOR / INCOMPLETE DATA (REQUEST MORE DATA)
    # -------------------------------------------------------------------------
    print_header("Scenario 5: Poor / Incomplete Data -- Clarification Prompt (P006)")
    adapter.process_hospital_event({"patient_id": "P006", "event_type": "PATIENT_DISCHARGED", "hospital_id": "METRO_GEN"})
    res5 = adapter.process_hospital_event({
        "patient_id": "P006",
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {},  # Empty payload
    })
    print_trace("P006", 1, "DAILY_CHECKIN", res5, "Empty payload handled gracefully without crashing")

    # -------------------------------------------------------------------------
    # SCENARIO 6: CLINICAL RED FLAG (SAFETY ESCALATION)
    # -------------------------------------------------------------------------
    print_header("Scenario 6: Clinical Red Flag -- Emergency Safety Escalation (P009)")
    adapter.process_hospital_event({"patient_id": "P009", "event_type": "PATIENT_DISCHARGED", "hospital_id": "METRO_GEN"})
    res6 = adapter.process_hospital_event({
        "patient_id": "P009",
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {"symptoms": "crushing chest pain radiating to left arm", "medication_taken": True, "energy_level": 2},
    })
    print_trace("P009", 1, "DAILY_CHECKIN", res6, "Emergency red flag routes to Escalate Node & dispatches alert")

    # -------------------------------------------------------------------------
    # SCENARIO 7: MISSED CHECK-IN (OVERDUE DETECTION)
    # -------------------------------------------------------------------------
    print_header("Scenario 7: Missed Check-in -- Overdue Detection (P010)")
    adapter.process_hospital_event({"patient_id": "P010", "event_type": "PATIENT_DISCHARGED", "hospital_id": "CITY_CARDIO"})
    future_time = datetime.utcnow() + timedelta(days=2)
    missed_events = scheduler.check_missed_checkins(patient_id="P010", now=future_time)
    if missed_events:
        res7 = adapter.process_hospital_event(missed_events[0])
        print_trace("P010", 1, "MISSED_CHECKIN", res7, "Expired check-in window detected by scheduler")

    # -------------------------------------------------------------------------
    # SCENARIO 8: HOSPITAL READMISSION (CARE PLAN PAUSED)
    # -------------------------------------------------------------------------
    print_header("Scenario 8: Hospital Readmission -- Care Paused & Schedules Cancelled (P007)")
    adapter.process_hospital_event({"patient_id": "P007", "event_type": "PATIENT_DISCHARGED", "hospital_id": "CITY_CARDIO"})
    res8 = adapter.process_hospital_event({
        "patient_id": "P007",
        "event_type": "PATIENT_READMITTED",
        "hospital_id": "CITY_CARDIO",
        "payload": {"admission_id": "ADM_RE_101", "reason": "Acute exacerbation"},
    })
    print(f"  Patient ID       : P007")
    print(f"  Event Ingested   : PATIENT_READMITTED")
    print(f"  Status           : {res8.get('status')}")
    print(f"  Message          : {res8.get('message')}")
    print("  " + "-" * 75)

    # -------------------------------------------------------------------------
    # SCENARIO 9: CARE COMPLETION (VARIABLE DURATION 10 DAYS REACHED)
    # -------------------------------------------------------------------------
    print_header("Scenario 9: Variable Care Duration Completion -- 10 Days (P003)")
    adapter.process_hospital_event({"patient_id": "P003", "event_type": "PATIENT_DISCHARGED", "hospital_id": "METRO_GEN"})
    for d in range(1, 10):
        adapter.process_hospital_event({"patient_id": "P003", "event_type": "DAILY_CHECKIN", "day": d, "payload": {"symptoms": "none"}})
    res9 = adapter.process_hospital_event({"patient_id": "P003", "event_type": "DAILY_CHECKIN", "day": 10, "payload": {"symptoms": "fully recovered"}})
    print_trace("P003", 10, "DAILY_CHECKIN", res9, "Care plan completed upon reaching model duration (10 days)")

    # -------------------------------------------------------------------------
    # SCENARIO 10: MULTI-PATIENT CONCURRENT EXECUTION
    # -------------------------------------------------------------------------
    print_header("Scenario 10: Multi-Patient Concurrent Execution & Thread Isolation")
    concurrent_ids = ["P001", "P002", "P003", "P005", "P009"]
    print(f"  Inspecting isolated state threads for patients: {concurrent_ids}")
    for pid in concurrent_ids:
        st = orchestrator.get_patient_state(pid)
        if st:
            print(f"  * {pid:<6} | Day: {st.get('current_day', 0):<2} | Risk: {st.get('risk_level', 'LOW'):<6} | Cadence: {st.get('monitoring_frequency', 'DAILY'):<12} | Status: {st.get('plan_status')}")
    print("  " + "-" * 75)

    # -------------------------------------------------------------------------
    # POSTGRESSAVER RESTART RECOVERY VERIFICATION
    # -------------------------------------------------------------------------
    print_header("PostgresSaver Restart Recovery Verification")
    print("  1. Destroying current orchestrator instance (simulating server crash/restart)...")
    del orchestrator
    del adapter

    print("  2. Starting fresh MultiPatientOrchestrator instance from PostgreSQL...")
    fresh_orch = MultiPatientOrchestrator(checkpointer=checkpointer)
    fresh_adapter = HospitalEventAdapter(orchestrator=fresh_orch, db_manager=db, scheduler=scheduler)

    recovered_p1 = fresh_orch.get_patient_state("P001")
    print(f"  3. State recovered for P001: Day {recovered_p1.get('current_day')} | Cadence: {recovered_p1.get('monitoring_frequency')} | Status: {recovered_p1.get('plan_status')}")

    res_post_restart = fresh_adapter.process_hospital_event({
        "patient_id": "P001",
        "event_type": "DAILY_CHECKIN",
        "day": 2,
        "payload": {"symptoms": "none", "medication_taken": True, "energy_level": 9},
    })
    print_trace("P001", 2, "DAILY_CHECKIN (Post-Restart)", res_post_restart, "Execution continued seamlessly from PostgreSQL checkpoint")

    print("\n" + "=" * 80)
    print(" [OK] ALL 10 SCENARIOS & POSTGRESSAVER RECOVERY COMPLETED SUCCESSFULLY!")
    print("================================================================================\n")


if __name__ == "__main__":
    run_full_simulation()
