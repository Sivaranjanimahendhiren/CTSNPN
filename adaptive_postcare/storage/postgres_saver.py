"""
PostgreSQL Checkpoint Saver for LangGraph.
Persists graph state snapshots and channel writes to PostgreSQL,
enabling patient state recovery across application restarts with thread isolation.
"""

from datetime import datetime
import json
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from sqlalchemy import Column, String, Text, DateTime, JSON, Integer, create_engine, select
from sqlalchemy.orm import Session
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from .database import Base, DatabaseSessionManager, get_db_session_manager


class LangGraphCheckpoint(Base):
    """TABLE: langgraph_checkpoints"""
    __tablename__ = "langgraph_checkpoints"

    thread_id = Column(String(64), primary_key=True)
    checkpoint_ns = Column(String(64), primary_key=True, default="")
    checkpoint_id = Column(String(64), primary_key=True)
    parent_checkpoint_id = Column(String(64), nullable=True)
    checkpoint = Column(JSON, nullable=False)
    metadata_ = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class LangGraphCheckpointWrite(Base):
    """TABLE: langgraph_checkpoint_writes"""
    __tablename__ = "langgraph_checkpoint_writes"

    thread_id = Column(String(64), primary_key=True)
    checkpoint_ns = Column(String(64), primary_key=True, default="")
    checkpoint_id = Column(String(64), primary_key=True)
    task_id = Column(String(64), primary_key=True)
    idx = Column(Integer, primary_key=True)
    channel = Column(String(255), nullable=False)
    value = Column(JSON, nullable=True)


class PostgresSaver(BaseCheckpointSaver):
    """
    Durable PostgreSQL Checkpoint Saver for LangGraph state machine.
    """

    def __init__(
        self,
        db_manager: Optional[DatabaseSessionManager] = None,
        serde: Optional[Any] = None,
    ):
        super().__init__(serde=serde or JsonPlusSerializer())
        self.db = db_manager or get_db_session_manager()
        self._init_tables()

    def _init_tables(self) -> None:
        """Ensures checkpoint tables exist in PostgreSQL database."""
        try:
            Base.metadata.create_all(
                bind=self.db.engine,
                tables=[
                    LangGraphCheckpoint.__table__,
                    LangGraphCheckpointWrite.__table__,
                ],
            )
        except Exception:
            pass

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """
        Retrieves the latest checkpoint tuple for the given thread_id and checkpoint_ns.
        """
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return None
        checkpoint_ns = config.get("configurable", {}).get("checkpoint_ns", "")
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")

        with self.db.session_scope() as session:
            query = session.query(LangGraphCheckpoint).filter(
                LangGraphCheckpoint.thread_id == str(thread_id),
                LangGraphCheckpoint.checkpoint_ns == str(checkpoint_ns),
            )
            if checkpoint_id:
                query = query.filter(LangGraphCheckpoint.checkpoint_id == str(checkpoint_id))
            else:
                query = query.order_by(LangGraphCheckpoint.created_at.desc())

            row = query.first()
            if not row:
                return None

            checkpoint_data = row.checkpoint
            metadata_data = row.metadata_ or {}

            parent_config = None
            if row.parent_checkpoint_id:
                parent_config = {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": row.parent_checkpoint_id,
                    }
                }

            return CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": row.checkpoint_id,
                    }
                },
                checkpoint=checkpoint_data,
                metadata=metadata_data,
                parent_config=parent_config,
                pending_writes=[],
            )

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        """
        Streams checkpoint tuples for the given thread_id.
        """
        if not config or "configurable" not in config:
            return

        thread_id = config["configurable"].get("thread_id")
        if not thread_id:
            return
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")

        with self.db.session_scope() as session:
            query = (
                session.query(LangGraphCheckpoint)
                .filter(
                    LangGraphCheckpoint.thread_id == str(thread_id),
                    LangGraphCheckpoint.checkpoint_ns == str(checkpoint_ns),
                )
                .order_by(LangGraphCheckpoint.created_at.desc())
            )
            if limit:
                query = query.limit(limit)

            rows = query.all()
            for row in rows:
                parent_config = None
                if row.parent_checkpoint_id:
                    parent_config = {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": row.parent_checkpoint_id,
                        }
                    }
                yield CheckpointTuple(
                    config={
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": row.checkpoint_id,
                        }
                    },
                    checkpoint=row.checkpoint,
                    metadata=row.metadata_ or {},
                    parent_config=parent_config,
                    pending_writes=[],
                )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """
        Saves a checkpoint for the given thread_id.
        """
        thread_id = str(config.get("configurable", {}).get("thread_id", ""))
        checkpoint_ns = str(config.get("configurable", {}).get("checkpoint_ns", ""))
        checkpoint_id = str(checkpoint.get("id", f"cp_{int(datetime.utcnow().timestamp()*1000)}"))
        parent_checkpoint_id = config.get("configurable", {}).get("checkpoint_id")

        with self.db.session_scope() as session:
            # Check if exists
            existing = (
                session.query(LangGraphCheckpoint)
                .filter(
                    LangGraphCheckpoint.thread_id == thread_id,
                    LangGraphCheckpoint.checkpoint_ns == checkpoint_ns,
                    LangGraphCheckpoint.checkpoint_id == checkpoint_id,
                )
                .first()
            )
            if existing:
                existing.checkpoint = checkpoint
                existing.metadata_ = metadata
                existing.parent_checkpoint_id = parent_checkpoint_id
            else:
                new_cp = LangGraphCheckpoint(
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    checkpoint_id=checkpoint_id,
                    parent_checkpoint_id=parent_checkpoint_id,
                    checkpoint=checkpoint,
                    metadata_=metadata,
                    created_at=datetime.utcnow(),
                )
                session.add(new_cp)

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """
        Saves checkpoint writes to the database.
        """
        thread_id = str(config.get("configurable", {}).get("thread_id", ""))
        checkpoint_ns = str(config.get("configurable", {}).get("checkpoint_ns", ""))
        checkpoint_id = str(config.get("configurable", {}).get("checkpoint_id", ""))

        if not thread_id or not writes:
            return

        with self.db.session_scope() as session:
            for idx, (channel, val) in enumerate(writes):
                write_entry = LangGraphCheckpointWrite(
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    checkpoint_id=checkpoint_id,
                    task_id=str(task_id),
                    idx=idx,
                    channel=str(channel),
                    value=val if isinstance(val, (dict, list, str, int, float, bool)) else str(val),
                )
                session.merge(write_entry)
