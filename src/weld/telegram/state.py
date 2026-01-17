"""SQLite state store for Telegram bot persistence."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import aiosqlite
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Schema version for migrations
SCHEMA_VERSION = 1

# Valid status values for type safety
ConversationState = Literal["idle", "awaiting_project", "awaiting_command", "running"]
RunStatus = Literal["pending", "running", "completed", "failed", "cancelled"]

SCHEMA_SQL = """
-- Schema versioning
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

-- User conversation contexts
CREATE TABLE IF NOT EXISTS contexts (
    user_id INTEGER PRIMARY KEY,
    current_project TEXT,
    conversation_state TEXT DEFAULT 'idle',
    last_message_id INTEGER,
    updated_at TEXT NOT NULL
);

-- Registered projects (mirrors config but allows runtime state)
CREATE TABLE IF NOT EXISTS projects (
    name TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    description TEXT,
    last_accessed_at TEXT,
    created_at TEXT NOT NULL
);

-- Command execution runs
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    project_name TEXT NOT NULL,
    command TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    result TEXT,
    error TEXT,
    FOREIGN KEY (project_name) REFERENCES projects(name)
);

CREATE INDEX IF NOT EXISTS idx_runs_user_id ON runs(user_id);
CREATE INDEX IF NOT EXISTS idx_runs_project_name ON runs(project_name);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
"""


class UserContext(BaseModel):
    """User conversation context."""

    user_id: int
    current_project: str | None = None
    conversation_state: ConversationState = "idle"
    last_message_id: int | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Project(BaseModel):
    """Project state record."""

    name: str
    path: str
    description: str | None = None
    last_accessed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Run(BaseModel):
    """Command execution run record."""

    id: int | None = None
    user_id: int
    project_name: str
    command: str
    status: RunStatus = "pending"
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    result: str | None = None
    error: str | None = None


def get_state_db_path() -> Path:
    """Get the default path to the state database.

    Returns:
        Path to ~/.weld/telegram/state.db
    """
    return Path.home() / ".weld" / "telegram" / "state.db"


def _serialize_datetime(dt: datetime | None) -> str | None:
    """Serialize datetime to ISO format string."""
    if dt is None:
        return None
    return dt.isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse ISO format string to datetime."""
    if value is None:
        return None
    return datetime.fromisoformat(value)


class StateStore:
    """Async SQLite state store for Telegram bot persistence.

    Manages user contexts, project state, and command run history.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialize state store.

        Args:
            db_path: Path to SQLite database. Use ':memory:' for in-memory.
                     Defaults to ~/.weld/telegram/state.db
        """
        if db_path is None:
            self.db_path = get_state_db_path()
        elif db_path == ":memory:":
            self.db_path = ":memory:"
        else:
            self.db_path = Path(db_path)

        self._conn: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Initialize database connection and schema.

        Creates parent directories if needed.
        Runs schema migrations if database version is outdated.

        Raises:
            aiosqlite.Error: If database initialization fails
            PermissionError: If unable to create database directory
        """
        # Create parent directory for file-based databases
        if self.db_path != ":memory:":
            db_path = Path(self.db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Initializing state store at {db_path}")

        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row

        await self._migrate_schema()

    async def _migrate_schema(self) -> None:
        """Run schema migrations if needed."""
        if self._conn is None:
            raise RuntimeError("Database not initialized")

        # Check current version
        current_version = 0
        try:
            async with self._conn.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    current_version = row["version"]
        except aiosqlite.OperationalError:
            # Table doesn't exist yet
            pass

        if current_version < SCHEMA_VERSION:
            logger.info(f"Migrating schema from v{current_version} to v{SCHEMA_VERSION}")
            await self._conn.executescript(SCHEMA_SQL)
            await self._conn.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
            )
            await self._conn.commit()
            logger.info("Schema migration complete")

    async def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> "StateStore":
        """Async context manager entry."""
        await self.init()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    # Context CRUD operations

    async def get_context(self, user_id: int) -> UserContext | None:
        """Get user context by user ID.

        Args:
            user_id: Telegram user ID

        Returns:
            UserContext if found, None otherwise
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized")

        async with self._conn.execute(
            "SELECT * FROM contexts WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return UserContext(
                user_id=row["user_id"],
                current_project=row["current_project"],
                conversation_state=row["conversation_state"],
                last_message_id=row["last_message_id"],
                updated_at=_parse_datetime(row["updated_at"]) or datetime.now(UTC),
            )

    async def upsert_context(self, context: UserContext) -> None:
        """Insert or update user context.

        Args:
            context: UserContext to save
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized")

        await self._conn.execute(
            """
            INSERT INTO contexts (user_id, current_project, conversation_state,
                                  last_message_id, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                current_project = excluded.current_project,
                conversation_state = excluded.conversation_state,
                last_message_id = excluded.last_message_id,
                updated_at = excluded.updated_at
            """,
            (
                context.user_id,
                context.current_project,
                context.conversation_state,
                context.last_message_id,
                _serialize_datetime(context.updated_at),
            ),
        )
        await self._conn.commit()

    async def delete_context(self, user_id: int) -> bool:
        """Delete user context.

        Args:
            user_id: Telegram user ID

        Returns:
            True if context was deleted, False if not found
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized")

        cursor = await self._conn.execute("DELETE FROM contexts WHERE user_id = ?", (user_id,))
        await self._conn.commit()
        return cursor.rowcount > 0

    # Project CRUD operations

    async def get_project(self, name: str) -> Project | None:
        """Get project by name.

        Args:
            name: Project name

        Returns:
            Project if found, None otherwise
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized")

        async with self._conn.execute("SELECT * FROM projects WHERE name = ?", (name,)) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return Project(
                name=row["name"],
                path=row["path"],
                description=row["description"],
                last_accessed_at=_parse_datetime(row["last_accessed_at"]),
                created_at=_parse_datetime(row["created_at"]) or datetime.now(UTC),
            )

    async def list_projects(self) -> list[Project]:
        """List all registered projects.

        Returns:
            List of all projects
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized")

        projects = []
        async with self._conn.execute("SELECT * FROM projects ORDER BY name") as cursor:
            async for row in cursor:
                projects.append(
                    Project(
                        name=row["name"],
                        path=row["path"],
                        description=row["description"],
                        last_accessed_at=_parse_datetime(row["last_accessed_at"]),
                        created_at=_parse_datetime(row["created_at"]) or datetime.now(UTC),
                    )
                )
        return projects

    async def upsert_project(self, project: Project) -> None:
        """Insert or update project.

        Args:
            project: Project to save
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized")

        await self._conn.execute(
            """
            INSERT INTO projects (name, path, description, last_accessed_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                path = excluded.path,
                description = excluded.description,
                last_accessed_at = excluded.last_accessed_at
            """,
            (
                project.name,
                project.path,
                project.description,
                _serialize_datetime(project.last_accessed_at),
                _serialize_datetime(project.created_at),
            ),
        )
        await self._conn.commit()

    async def delete_project(self, name: str) -> bool:
        """Delete project by name.

        Args:
            name: Project name

        Returns:
            True if project was deleted, False if not found
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized")

        cursor = await self._conn.execute("DELETE FROM projects WHERE name = ?", (name,))
        await self._conn.commit()
        return cursor.rowcount > 0

    async def touch_project(self, name: str) -> None:
        """Update project last_accessed_at timestamp.

        Args:
            name: Project name
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized")

        now = _serialize_datetime(datetime.now(UTC))
        await self._conn.execute(
            "UPDATE projects SET last_accessed_at = ? WHERE name = ?", (now, name)
        )
        await self._conn.commit()

    # Run CRUD operations

    async def create_run(self, run: Run) -> int:
        """Create a new command run record.

        Args:
            run: Run to create (id field is ignored)

        Returns:
            ID of the created run
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized")

        cursor = await self._conn.execute(
            """
            INSERT INTO runs (user_id, project_name, command, status,
                              started_at, completed_at, result, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.user_id,
                run.project_name,
                run.command,
                run.status,
                _serialize_datetime(run.started_at),
                _serialize_datetime(run.completed_at),
                run.result,
                run.error,
            ),
        )
        await self._conn.commit()
        return cursor.lastrowid or 0

    async def get_run(self, run_id: int) -> Run | None:
        """Get run by ID.

        Args:
            run_id: Run ID

        Returns:
            Run if found, None otherwise
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized")

        async with self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return Run(
                id=row["id"],
                user_id=row["user_id"],
                project_name=row["project_name"],
                command=row["command"],
                status=row["status"],
                started_at=_parse_datetime(row["started_at"]) or datetime.now(UTC),
                completed_at=_parse_datetime(row["completed_at"]),
                result=row["result"],
                error=row["error"],
            )

    async def update_run(self, run: Run) -> bool:
        """Update an existing run.

        Args:
            run: Run to update (must have valid id)

        Returns:
            True if run was updated, False if not found
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized")

        if run.id is None:
            raise ValueError("Run must have an id to update")

        cursor = await self._conn.execute(
            """
            UPDATE runs SET
                status = ?,
                started_at = ?,
                completed_at = ?,
                result = ?,
                error = ?
            WHERE id = ?
            """,
            (
                run.status,
                _serialize_datetime(run.started_at),
                _serialize_datetime(run.completed_at),
                run.result,
                run.error,
                run.id,
            ),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def list_runs_by_user(
        self, user_id: int, limit: int = 10, status: RunStatus | None = None
    ) -> list[Run]:
        """List runs for a user.

        Args:
            user_id: Telegram user ID
            limit: Maximum number of runs to return
            status: Optional status filter

        Returns:
            List of runs, most recent first
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized")

        if status:
            query = """
                SELECT * FROM runs
                WHERE user_id = ? AND status = ?
                ORDER BY started_at DESC
                LIMIT ?
            """
            params = (user_id, status, limit)
        else:
            query = """
                SELECT * FROM runs
                WHERE user_id = ?
                ORDER BY started_at DESC
                LIMIT ?
            """
            params = (user_id, limit)

        runs = []
        async with self._conn.execute(query, params) as cursor:
            async for row in cursor:
                runs.append(
                    Run(
                        id=row["id"],
                        user_id=row["user_id"],
                        project_name=row["project_name"],
                        command=row["command"],
                        status=row["status"],
                        started_at=_parse_datetime(row["started_at"]) or datetime.now(UTC),
                        completed_at=_parse_datetime(row["completed_at"]),
                        result=row["result"],
                        error=row["error"],
                    )
                )
        return runs

    async def list_runs_by_project(self, project_name: str, limit: int = 10) -> list[Run]:
        """List runs for a project.

        Args:
            project_name: Project name
            limit: Maximum number of runs to return

        Returns:
            List of runs, most recent first
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized")

        runs = []
        async with self._conn.execute(
            """
            SELECT * FROM runs
            WHERE project_name = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (project_name, limit),
        ) as cursor:
            async for row in cursor:
                runs.append(
                    Run(
                        id=row["id"],
                        user_id=row["user_id"],
                        project_name=row["project_name"],
                        command=row["command"],
                        status=row["status"],
                        started_at=_parse_datetime(row["started_at"]) or datetime.now(UTC),
                        completed_at=_parse_datetime(row["completed_at"]),
                        result=row["result"],
                        error=row["error"],
                    )
                )
        return runs
