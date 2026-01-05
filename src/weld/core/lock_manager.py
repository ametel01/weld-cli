"""Lock manager for weld run concurrency control.

Provides PID-based file locking to prevent concurrent modifications
to weld runs. Includes stale lock detection for crash recovery.

Uses atomic file creation (O_CREAT | O_EXCL) to prevent TOCTOU races.
"""

import contextlib
import os
from datetime import datetime, timedelta
from pathlib import Path

from ..models import Lock

LOCK_FILE = "active.lock"
STALE_TIMEOUT_SECONDS = 3600  # 1 hour
MAX_LOCK_RETRIES = 3  # Max retries when clearing stale locks


class LockError(Exception):
    """Error acquiring or managing lock."""


def _lock_path(weld_dir: Path) -> Path:
    """Get path to lock file."""
    return weld_dir / LOCK_FILE


def _is_pid_running(pid: int) -> bool:
    """Check if a process with given PID is running."""
    try:
        os.kill(pid, 0)  # Signal 0 doesn't kill, just checks
        return True
    except OSError:
        return False


def get_current_lock(weld_dir: Path) -> Lock | None:
    """Get current lock if it exists and is valid.

    Args:
        weld_dir: Path to .weld directory

    Returns:
        Lock if valid lock exists, None otherwise
    """
    lock_path = _lock_path(weld_dir)
    if not lock_path.exists():
        return None

    try:
        content = lock_path.read_text()
        return Lock.model_validate_json(content)
    except Exception:
        # Corrupted lock file - treat as no lock
        return None


def is_stale_lock(lock: Lock, timeout_seconds: int = STALE_TIMEOUT_SECONDS) -> bool:
    """Check if lock is stale (PID dead or timeout exceeded).

    Args:
        lock: Lock to check
        timeout_seconds: Max time since heartbeat before considered stale

    Returns:
        True if lock is stale and should be cleared
    """
    # Check if owning process is dead
    if not _is_pid_running(lock.pid):
        return True

    # Check if heartbeat is too old
    age = datetime.now() - lock.last_heartbeat
    return age > timedelta(seconds=timeout_seconds)


def _try_atomic_create(lock_path: Path, lock: Lock) -> bool:
    """Attempt atomic lock file creation.

    Uses O_CREAT | O_EXCL flags for atomicity - if file exists,
    open() fails immediately rather than overwriting.

    Returns:
        True if lock was created, False if file already exists
    """
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, lock.model_dump_json(indent=2).encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return False


def acquire_lock(weld_dir: Path, run_id: str, command: str) -> Lock:
    """Acquire lock for run modification.

    Uses atomic file creation to prevent TOCTOU race conditions.

    Args:
        weld_dir: Path to .weld directory
        run_id: ID of run being modified
        command: Command acquiring the lock

    Returns:
        Lock object if acquired

    Raises:
        LockError: If another process holds an active lock
    """
    lock_path = _lock_path(weld_dir)
    lock = Lock(
        pid=os.getpid(),
        run_id=run_id,
        command=command,
    )

    for _ in range(MAX_LOCK_RETRIES):
        # Try atomic creation first
        if _try_atomic_create(lock_path, lock):
            return lock

        # File exists - check if it's our lock or stale
        existing = get_current_lock(weld_dir)
        if existing is None:
            # Corrupted or removed between attempts - retry
            continue

        if existing.pid == os.getpid():
            # We already own the lock - update it
            lock_path.write_text(lock.model_dump_json(indent=2))
            return lock

        if is_stale_lock(existing):
            # Clear stale lock and retry
            with contextlib.suppress(FileNotFoundError):
                lock_path.unlink()
            continue

        # Active lock held by another process
        raise LockError(
            f"Run already in progress (PID {existing.pid}, command: {existing.command})"
        )

    # Exhausted retries
    raise LockError("Failed to acquire lock after multiple attempts")


def release_lock(weld_dir: Path) -> None:
    """Release lock if owned by current process.

    Args:
        weld_dir: Path to .weld directory
    """
    lock_path = _lock_path(weld_dir)
    existing = get_current_lock(weld_dir)

    if existing and existing.pid == os.getpid():
        lock_path.unlink(missing_ok=True)


def update_heartbeat(weld_dir: Path) -> None:
    """Update lock heartbeat timestamp.

    Should be called periodically during long operations.

    Args:
        weld_dir: Path to .weld directory
    """
    existing = get_current_lock(weld_dir)
    if existing and existing.pid == os.getpid():
        existing.last_heartbeat = datetime.now()
        _lock_path(weld_dir).write_text(existing.model_dump_json(indent=2))
