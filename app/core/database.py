"""Database connection and management with SQLAlchemy."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4
from sqlalchemy.ext.asyncio import (
    AsyncSession, 
    create_async_engine, 
    async_sessionmaker,
    AsyncEngine
)
from sqlalchemy.pool import QueuePool
from sqlalchemy import text
from app.config.settings import settings
from app.models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Database connection manager with SQLAlchemy async support."""
    
    def __init__(self):
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker] = None
        self._connection_string = self._build_connection_string()
        self._task_sessions: Dict["asyncio.Task", AsyncSession] = {}
        self._closing: set = set()  # in-flight deferred session.close() tasks
    
    def _build_connection_string(self) -> str:
        """Build database connection string from settings."""
        # Convert postgresql:// to postgresql+asyncpg:// for async support
        return settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
    
    async def connect(self) -> None:
        """Initialize database engine and session factory."""
        try:
            logger.info("Connecting to database...")
            
            # Create async engine with connection pooling. Many repository
            # methods fall back to `db.session` instead of `async with
            # db.get_session()` — that property reuses one session per
            # asyncio task (see DatabaseManager.session), so live
            # connections scale with concurrency, not with total repository
            # calls.
            #
            # Pool size comes from settings because the two workloads that share
            # this manager are shaped differently: the API is a 512 MB Render
            # instance answering a handful of people, while the ingest job processes
            # jobs concurrently and starves at a small pool. At 3+2 an ingest
            # run spent 10 seconds timing out per job and wrote a single row
            # in 50 minutes -- "QueuePool limit of size 3 overflow 2 reached".
            #
            # Raising it is only safe on Supabase's TRANSACTION pooler (6543),
            # which multiplexes clients. Session mode (5432) caps the whole
            # project at 15 connections, and that ceiling is shared with the
            # API and with alembic during a Render build.
            #
            # One refresh request needs TWO connections: the endpoint holds
            # one while is_token_revoked opens its own session.
            self.engine = create_async_engine(
                self._connection_string,
                poolclass=QueuePool,
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_timeout=10,
                pool_recycle=300,
                pool_pre_ping=True,
                # Makes the transaction-mode pooler (port 6543) usable, which
                # is the real cure for EMAXCONNSESSION: it multiplexes many
                # clients instead of capping the project at 15. Prepared
                # statements do not survive a pooler that hands out a
                # different backend per transaction, so both caches have to
                # go -- asyncpg's own (statement_cache_size) and the one
                # SQLAlchemy's asyncpg dialect keeps
                # (prepared_statement_cache_size, a DBAPI-level argument).
                # Harmless on session mode (5432), so switching ports is now
                # purely a DATABASE_URL change with no code edit.
                connect_args={
                    "statement_cache_size": 0,
                    "prepared_statement_cache_size": 0,
                    # Disabling the caches is not enough: SQLAlchemy still
                    # PREPAREs each statement, and its default name generator
                    # reuses names per connection. Through a transaction-mode
                    # pooler those land on different backends and collide with
                    # "prepared statement already exists". Unique names per
                    # statement are the documented fix (see the asyncpg
                    # dialect docs, sqlalchemy issue #6467).
                    "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
                },
                echo=settings.debug,  # Enable SQL logging in debug mode
            )
            
            # Create session factory
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info("Database engine created successfully")
            
            # Test the connection
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
                logger.info("Database connection test successful")
                
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Close database engine."""
        if self.engine:
            logger.info("Closing database engine...")
            # Task-scoped sessions close via a done-callback that schedules
            # (but doesn't await) their close — for a task whose callback
            # hasn't run yet by the time the process is winding down, close
            # explicitly here so dispose() doesn't tear down a checked-out
            # connection.
            for session in list(self._task_sessions.values()):
                try:
                    await session.close()
                except Exception as e:
                    logger.debug(f"Error closing session during disconnect: {e}")
            self._task_sessions.clear()
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None
            logger.info("Database engine closed")
    
    @property
    def session(self) -> AsyncSession:
        """One AsyncSession per asyncio task, auto-closed when that task finishes.

        Used by repository methods as a fallback when no session is passed
        in (`session = session or db.session`). None of those call sites
        close what they get back — a single job's processing makes on the
        order of 8 repository calls (dedup lookups, company resolution,
        job create, job_details upsert, ...), and a naive "new session per
        call" gave 10 concurrent jobs x ~8 sessions = 80 simultaneously
        open connections, exhausting the pool mid-batch. Reusing one
        session per task bounds live connections to the concurrency level
        instead. asyncio.gather() wraps each concurrently-processed job in
        its own Task, so this scopes correctly to "one session per job" —
        not "one session for the whole ingest run" — even though nothing
        the caller does looks task-aware.

        Prefer `get_session()` / `get_db_session()` for FastAPI
        dependencies, which handle commit/rollback/close explicitly and
        don't need this safety net.
        """
        if not self.session_factory:
            raise RuntimeError("Database not initialized")

        try:
            task = asyncio.current_task()
        except RuntimeError:
            task = None

        if task is None:
            # No enclosing task — caller owns this session's lifecycle.
            return self.session_factory()

        existing = self._task_sessions.get(task)
        if existing is not None:
            return existing

        session = self.session_factory()
        self._task_sessions[task] = session
        self._schedule_session_cleanup(task, session)
        return session

    async def release_task_session(self) -> None:
        """Close the current task's session now instead of when the task ends.
        Batch ingest calls this as each job finishes so its connection is back
        in the pool before the next job (waiting on the semaphore) starts."""
        task = asyncio.current_task()
        session = self._task_sessions.pop(task, None) if task else None
        if session is not None:
            await session.close()

    def _schedule_session_cleanup(self, task: "asyncio.Task", session: AsyncSession) -> None:
        """Close `session` once `task` completes."""
        def _close_when_done(_task: "asyncio.Task") -> None:
            self._task_sessions.pop(_task, None)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # asyncio keeps only weak references to tasks: an unreferenced
                    # close() can be garbage-collected mid-flight, leaking its
                    # connection until the pool is exhausted. Hold it until done.
                    closer = loop.create_task(session.close())
                    self._closing.add(closer)
                    closer.add_done_callback(self._closing.discard)
            except Exception as e:
                logger.debug(f"Deferred session close failed: {e}")

        task.add_done_callback(_close_when_done)

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        if not self.session_factory:
            raise RuntimeError("Database not initialized")
        
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def create_tables(self) -> None:
        """Create all database tables."""
        if not self.engine:
            raise RuntimeError("Database engine not initialized")
        
        logger.info("Creating database tables...")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    
    async def drop_tables(self) -> None:
        """Drop all database tables."""
        if not self.engine:
            raise RuntimeError("Database engine not initialized")
        
        logger.info("Dropping database tables...")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.info("Database tables dropped successfully")
    
    async def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            if not self.engine:
                return False
            
            async with self.engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# Global database manager instance
db = DatabaseManager()


# Dependency for getting database session
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for getting database session."""
    async with db.get_session() as session:
        yield session


# Alias — some callers import get_db() instead of get_db_session()
get_db = get_db_session
