"""
SQLAlchemy Database connection and session management for PostgreSQL and testing engines.
Supports PostgreSQL connection strings with automatic SQLite fallback for lightweight environments.
"""

import os
from contextlib import contextmanager
from typing import Generator, Optional
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session, Session

Base = declarative_base()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enforces foreign key constraints for SQLite testing connections."""
    if "sqlite" in type(dbapi_connection).__module__:
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        except Exception:
            pass


class DatabaseSessionManager:
    """
    Manages SQLAlchemy engine, session lifecycle, and table creation.
    """

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.getenv("DATABASE_URL", "sqlite:///:memory:")
        
        # Configure engine arguments
        engine_kwargs = {}
        if self.db_url.startswith("sqlite"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in self.db_url:
                engine_kwargs["poolclass"] = StaticPool
        else:
            engine_kwargs["pool_pre_ping"] = True
            engine_kwargs["pool_size"] = 10
            engine_kwargs["max_overflow"] = 20

        try:
            self.engine = create_engine(self.db_url, **engine_kwargs)
        except Exception:
            # Fallback to in-memory SQLite if driver connection fails
            self.db_url = "sqlite:///:memory:"
            self.engine = create_engine(
                "sqlite:///:memory:",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )

        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.scoped_session = scoped_session(self.session_factory)
        self.init_db()

    def init_db(self) -> None:
        """Creates all registered tables."""
        # Ensure models are imported before creating tables
        from . import models  # noqa: F401
        Base.metadata.create_all(bind=self.engine)

    def drop_db(self) -> None:
        """Drops all registered tables."""
        Base.metadata.drop_all(bind=self.engine)

    def get_session(self) -> Session:
        """Returns a new database session."""
        return self.scoped_session()

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Transactional scope around a series of operations."""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


_GLOBAL_DB_SESSION_MANAGER: Optional[DatabaseSessionManager] = None


def get_db_session_manager(db_url: Optional[str] = None) -> DatabaseSessionManager:
    """Returns a singleton or configured DatabaseSessionManager."""
    global _GLOBAL_DB_SESSION_MANAGER
    if _GLOBAL_DB_SESSION_MANAGER is None or db_url is not None:
        _GLOBAL_DB_SESSION_MANAGER = DatabaseSessionManager(db_url=db_url)
        _GLOBAL_DB_SESSION_MANAGER.init_db()
    return _GLOBAL_DB_SESSION_MANAGER


# Backward-compatible aliases
DatabaseManager = DatabaseSessionManager
get_db_manager = get_db_session_manager
