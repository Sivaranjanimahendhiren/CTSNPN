"""
Tests for STAGE 7: LangGraph PostgreSQL Checkpoint Persistence.
Validates PostgresSaver, thread_id state isolation, checkpoint survival across
application restarts, and MemorySaver fallback.
"""

import pytest
from adaptive_postcare.storage.database import DatabaseSessionManager
from adaptive_postcare.storage.postgres_saver import PostgresSaver, LangGraphCheckpoint, LangGraphCheckpointWrite
from adaptive_postcare.orchestrator import MultiPatientOrchestrator
from adaptive_postcare.graph.builder import get_checkpointer
from langgraph.checkpoint.memory import MemorySaver


@pytest.fixture
def test_db():
    """Provides isolated test database."""
    manager = DatabaseSessionManager(db_url="sqlite:///:memory:")
    manager.init_db()
    return manager


@pytest.fixture
def postgres_saver(test_db):
    """Provides PostgresSaver connected to isolated test database."""
    return PostgresSaver(db_manager=test_db)


# =========================================================================
# 1. TEST POSTGRES SAVER INITIALIZATION & TABLE CREATION
# =========================================================================
def test_postgres_saver_init_and_tables(test_db):
    """Verify PostgresSaver initializes and creates checkpoint tables."""
    saver = PostgresSaver(db_manager=test_db)
    assert saver is not None

    with test_db.session_scope() as session:
        # Tables exist and can be queried
        count = session.query(LangGraphCheckpoint).count()
        assert count == 0


# =========================================================================
# 2. TEST THREAD ID STATE ISOLATION IN POSTGRES SAVER
# =========================================================================
def test_postgres_saver_thread_isolation(postgres_saver):
    """Verify distinct patients maintain isolated checkpoints."""
    config_p1 = {"configurable": {"thread_id": "P001", "checkpoint_ns": ""}}
    config_p2 = {"configurable": {"thread_id": "P002", "checkpoint_ns": ""}}

    cp_p1 = {
        "v": 1,
        "id": "cp_p1_1",
        "ts": "2026-08-21T10:00:00Z",
        "channel_values": {"patient_id": "P001", "current_day": 3, "monitoring_frequency": "TWICE_DAILY"},
        "channel_versions": {},
        "versions_seen": {},
    }
    cp_p2 = {
        "v": 1,
        "id": "cp_p2_1",
        "ts": "2026-08-21T10:00:00Z",
        "channel_values": {"patient_id": "P002", "current_day": 1, "monitoring_frequency": "DAILY"},
        "channel_versions": {},
        "versions_seen": {},
    }

    postgres_saver.put(config_p1, cp_p1, {"step": 3}, {})
    postgres_saver.put(config_p2, cp_p2, {"step": 1}, {})

    tup_p1 = postgres_saver.get_tuple(config_p1)
    tup_p2 = postgres_saver.get_tuple(config_p2)

    assert tup_p1 is not None
    assert tup_p2 is not None
    assert tup_p1.checkpoint["channel_values"]["patient_id"] == "P001"
    assert tup_p1.checkpoint["channel_values"]["current_day"] == 3
    assert tup_p2.checkpoint["channel_values"]["patient_id"] == "P002"
    assert tup_p2.checkpoint["channel_values"]["current_day"] == 1


# =========================================================================
# 3. TEST STATE RECOVERY ACROSS APPLICATION RESTARTS
# =========================================================================
def test_orchestrator_state_recovery_across_restarts(postgres_saver):
    """
    Verify state persists across orchestrator instances:
    1. Instance 1 registers patient and processes Day 1 event.
    2. Instance 1 is destroyed (simulating server restart).
    3. Instance 2 starts up, recovers state, and executes Day 2 event.
    """
    # --- INSTANCE 1 ---
    orch1 = MultiPatientOrchestrator(checkpointer=postgres_saver)
    orch1.register_patient(
        patient_id="P_RESTART_01",
        risk_score=0.75,
        risk_level="HIGH",
        care_duration_days=20,
    )

    res1 = orch1.process_patient_event({
        "patient_id": "P_RESTART_01",
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {"symptoms": "none", "medication_taken": True, "energy_level": 8},
    })
    assert res1["current_day"] == 1
    assert len(res1["feedback_history"]) == 1

    # --- SIMULATE APPLICATION RESTART ---
    del orch1

    # --- INSTANCE 2 (Fresh Instance with empty in-memory cache) ---
    orch2 = MultiPatientOrchestrator(checkpointer=postgres_saver)
    assert "P_RESTART_01" not in orch2._patient_states

    # Hydrate state from PostgreSQL checkpointer
    recovered_state = orch2.get_patient_state("P_RESTART_01")
    assert recovered_state is not None
    assert recovered_state["patient_id"] == "P_RESTART_01"
    assert recovered_state["current_day"] == 1
    assert len(recovered_state["feedback_history"]) == 1

    # Process Day 2 on recovered instance
    res2 = orch2.process_patient_event({
        "patient_id": "P_RESTART_01",
        "event_type": "DAILY_CHECKIN",
        "day": 2,
        "payload": {"symptoms": "none", "medication_taken": True, "energy_level": 9},
    })
    assert res2["current_day"] == 2
    assert len(res2["feedback_history"]) == 2


# =========================================================================
# 4. TEST MULTI-PATIENT CONCURRENCY WITH POSTGRES SAVER
# =========================================================================
def test_multi_patient_concurrency_with_postgres_saver(postgres_saver):
    """Verify multiple patients using the same graph instance store checkpoints independently."""
    orch = MultiPatientOrchestrator(checkpointer=postgres_saver)

    orch.register_patient("P_MULTI_A", 0.85, "HIGH", 30)
    orch.register_patient("P_MULTI_B", 0.30, "LOW", 10)

    orch.process_patient_event({
        "patient_id": "P_MULTI_A",
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {"symptoms": "wound pain", "medication_taken": True},
    })
    orch.process_patient_event({
        "patient_id": "P_MULTI_B",
        "event_type": "DAILY_CHECKIN",
        "day": 1,
        "payload": {"symptoms": "none", "medication_taken": True},
    })

    st_a = orch.get_patient_state("P_MULTI_A")
    st_b = orch.get_patient_state("P_MULTI_B")

    assert st_a["patient_id"] == "P_MULTI_A"
    assert st_a["care_duration_days"] == 30
    assert st_b["patient_id"] == "P_MULTI_B"
    assert st_b["care_duration_days"] == 10


# =========================================================================
# 5. TEST MEMORY SAVER FALLBACK
# =========================================================================
def test_memory_saver_fallback(monkeypatch):
    """Verify MemorySaver is returned when configured as memory backend."""
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_BACKEND", "memory")
    cp = get_checkpointer()
    assert isinstance(cp, MemorySaver)
