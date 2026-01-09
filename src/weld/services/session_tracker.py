"""Session tracking service for weld.

This module manages the session registry, which tracks Claude Code sessions
and their associated file changes. The registry persists to JSONL format
at `.weld/sessions/registry.jsonl`.

Design notes:
- Sessions are loaded lazily on first access
- Corrupted JSONL lines are skipped with a warning (graceful degradation)
- Save after every mutation to prevent data loss
- Concurrent writes use last-write-wins (acceptable for single-user tool)
"""

import contextlib
import json
import logging
import time
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from ..models.session import SessionActivity, TrackedSession
from .session_detector import detect_current_session, get_session_id

logger = logging.getLogger(__name__)

# Directories to exclude from file snapshots (performance optimization)
# Note: These are matched as substrings against path parts, not glob patterns
SNAPSHOT_EXCLUDES = {
    ".git",
    ".weld",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".tox",
    ".nox",
    ".eggs",
    ".egg-info",  # Matches any directory ending in .egg-info (e.g., my_package.egg-info)
    ".coverage",
    "htmlcov",
}

# Timeout for file snapshots in large repositories (seconds)
FILE_SNAPSHOT_TIMEOUT = 5


class SessionRegistry:
    """Manages .weld/sessions/registry.jsonl.

    The registry stores TrackedSession objects in JSONL format, one session
    per line. Each session tracks activities (file changes) that occurred
    during weld commands.

    Attributes:
        registry_path: Path to the registry.jsonl file
    """

    def __init__(self, registry_path: Path) -> None:
        """Initialize the registry.

        Args:
            registry_path: Path to the registry.jsonl file
        """
        self.registry_path = registry_path
        self._sessions: dict[str, TrackedSession] = {}
        self._load()

    def _load(self) -> None:
        """Load sessions from JSONL file.

        Handles corrupted entries gracefully by skipping them and logging
        a warning. This ensures partial corruption doesn't lose all data.
        """
        if not self.registry_path.exists():
            return

        for line_num, line in enumerate(self.registry_path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                session = TrackedSession.model_validate_json(line)
                self._sessions[session.session_id] = session
            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning(f"Skipping corrupted registry entry at line {line_num}: {e}")

    def save(self) -> None:
        """Persist sessions to JSONL file.

        Creates the parent directory if it doesn't exist.
        """
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [s.model_dump_json() for s in self._sessions.values()]
        self.registry_path.write_text("\n".join(lines) + "\n" if lines else "")

    def get(self, session_id: str) -> TrackedSession | None:
        """Get a session by ID.

        Args:
            session_id: The session UUID

        Returns:
            TrackedSession if found, None otherwise
        """
        return self._sessions.get(session_id)

    def record_activity(
        self,
        session_id: str,
        session_file: str,
        command: str,
        files_created: list[str],
        files_modified: list[str],
        completed: bool = True,
    ) -> None:
        """Record activity for a session.

        Creates a new session if one doesn't exist for the given ID.
        Appends the activity and updates last_activity timestamp.

        Args:
            session_id: UUID from Claude session filename
            session_file: Absolute path to the .jsonl session file
            command: Weld command that was executed (e.g., "research", "implement")
            files_created: List of relative paths to files created
            files_modified: List of relative paths to files modified
            completed: Whether the command completed successfully
        """
        # Validate session file exists (warn if not)
        if not Path(session_file).exists():
            logger.warning(
                f"Session file not found: {session_file}. "
                "Transcript may not be available for commit."
            )

        now = datetime.now(UTC)
        activity = SessionActivity(
            command=command,
            timestamp=now,
            files_created=files_created,
            files_modified=files_modified,
            completed=completed,
        )

        if session_id not in self._sessions:
            self._sessions[session_id] = TrackedSession(
                session_id=session_id,
                session_file=session_file,
                first_seen=now,
                last_activity=now,
                activities=[activity],
            )
        else:
            session = self._sessions[session_id]
            session.activities.append(activity)
            session.last_activity = now

        self.save()

    def prune_session(self, session_id: str) -> None:
        """Remove session from registry.

        Typically called after a successful commit to clean up
        sessions that have been committed.

        Args:
            session_id: The session UUID to remove
        """
        self._sessions.pop(session_id, None)
        self.save()

    @property
    def sessions(self) -> dict[str, TrackedSession]:
        """Get all tracked sessions.

        Returns:
            Dict mapping session_id to TrackedSession
        """
        return self._sessions


def get_registry(weld_dir: Path) -> SessionRegistry:
    """Get session registry for a weld project.

    Args:
        weld_dir: Path to the .weld directory

    Returns:
        SessionRegistry instance for the project
    """
    return SessionRegistry(weld_dir / "sessions" / "registry.jsonl")


def _should_exclude_path(path: Path) -> bool:
    """Check if a path should be excluded from file snapshots.

    Matches path parts against SNAPSHOT_EXCLUDES using substring matching
    to handle patterns like '.egg-info' which can appear as suffixes
    (e.g., 'my_package.egg-info').

    Args:
        path: Path to check

    Returns:
        True if the path should be excluded
    """
    for part in path.parts:
        for exc in SNAPSHOT_EXCLUDES:
            # Exact match for most patterns, substring match for suffix patterns
            if part == exc or (exc.startswith(".") and part.endswith(exc)):
                return True
    return False


def get_file_snapshot(repo_root: Path, timeout: float = FILE_SNAPSHOT_TIMEOUT) -> dict[str, float]:
    """Get {relative_path: mtime} for all files in repo.

    Excludes common build/cache directories for performance.
    For a 50K file repo, this avoids scanning irrelevant directories.

    Uses a timeout to prevent blocking on extremely large repositories.
    Returns partial snapshot if timeout is exceeded (best-effort tracking).

    Args:
        repo_root: Path to repository root
        timeout: Maximum time in seconds (default 5s, accepts float)

    Returns:
        Dict mapping relative file paths to modification times.
        Returns partial snapshot if timeout exceeded.
    """
    start = time.time()
    snapshot = {}

    for f in repo_root.rglob("*"):
        # Check for timeout to prevent blocking on large repos
        if time.time() - start > timeout:
            logger.warning(
                f"File snapshot timed out after {timeout}s ({len(snapshot)} files scanned). "
                "Using partial snapshot for tracking."
            )
            break

        # Skip excluded directories early for performance
        if _should_exclude_path(f):
            continue
        if f.is_file():
            try:
                rel = str(f.relative_to(repo_root))
                snapshot[rel] = f.stat().st_mtime
            except (OSError, ValueError):
                pass

    return snapshot


def compute_changes(
    before: dict[str, float],
    after: dict[str, float],
) -> tuple[list[str], list[str]]:
    """Compute created and modified files between snapshots.

    Args:
        before: Snapshot before operation {path: mtime}
        after: Snapshot after operation {path: mtime}

    Returns:
        Tuple of (files_created, files_modified)
    """
    created = [f for f in after if f not in before]
    modified = [f for f in after if f in before and after[f] != before[f]]
    return created, modified


@contextlib.contextmanager
def track_session_activity(
    weld_dir: Path,
    repo_root: Path,
    command: str,
) -> Generator[None, None, None]:
    """Context manager to track file changes during a command.

    Usage:
        with track_session_activity(weld_dir, repo_root, "implement"):
            # Do work that modifies files
            run_claude(...)

    Records activity to registry if changes were made.
    Handles interruptions by marking activity as incomplete.
    Gracefully handles tracking failures without breaking the command.

    Args:
        weld_dir: Path to .weld directory
        repo_root: Path to repository root
        command: Weld command name being executed (e.g., "implement")

    Yields:
        Nothing - context manager for side effects only
    """
    session_file = detect_current_session(repo_root)
    if not session_file:
        logger.debug(f"No Claude session detected, skipping tracking for {command}")
        yield  # No session to track
        return

    # Try to capture pre-command snapshot
    before = None
    try:
        before = get_file_snapshot(repo_root)
    except (OSError, PermissionError, ValueError) as e:
        logger.error(f"Failed to capture pre-command snapshot: {e}")
        yield  # Run command anyway
        return

    # Run command and track completion status
    completed = False
    try:
        yield
        completed = True
    finally:
        # Try to save tracking data, but don't let failures break the command
        try:
            after = get_file_snapshot(repo_root)
            created, modified = compute_changes(before, after)

            # Only record if changes were made
            if created or modified:
                session_id = get_session_id(session_file)
                registry = get_registry(weld_dir)
                registry.record_activity(
                    session_id=session_id,
                    session_file=str(session_file),
                    command=command,
                    files_created=created,
                    files_modified=modified,
                    completed=completed,
                )
                logger.debug(
                    f"Tracked {len(created)} created, {len(modified)} modified files "
                    f"for session {session_id[:8]}... (command: {command}, completed: {completed})"
                )
        except (OSError, PermissionError, ValidationError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to save session activity: {e}")
        except Exception as e:
            # Unexpected errors - log with warning to help debugging
            logger.error(f"Unexpected error saving session activity: {type(e).__name__}: {e}")
