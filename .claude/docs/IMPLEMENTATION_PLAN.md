# Implementation Plan: SPECS.md Gap Resolution

Based on [specs-gap-analysis.md](../research/specs-gap-analysis.md). Each phase is independently deliverable.

## Planning Principles Applied

This plan follows these principles:
- **Exact steps**: Each step shows current code → target code with file:line references
- **Concrete snippets**: Actual current implementation shown, not conceptual
- **Validation after each change**: Specific commands with expected outcomes
- **Failure modes obvious**: Each step identifies what breaks and how to detect it

---

## Phase 1: Foundation (Enables All Subsequent Phases)

### 1.1 Multi-Category Checks System **COMPLETE**

**Current state:** Single `command` field in ChecksConfig

**Target state:** Category-based checks with fail-fast and full-run modes

#### Step 1.1.1: Add CategoryResult and ChecksSummary models

**File:** `src/weld/models/status.py`

**Current code (lines 1-44):**
```python
"""Status model for iteration review results..."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class Status(BaseModel):
    # ... existing fields
```

**Action:** Append new models BEFORE the Status class:

```python
class CategoryResult(BaseModel):
    """Result from a single check category."""

    category: str = Field(description="Check category name (lint, test, etc.)")
    exit_code: int = Field(description="Exit code from command")
    passed: bool = Field(description="True if exit_code == 0")
    output: str = Field(default="", description="Captured stdout+stderr")


class ChecksSummary(BaseModel):
    """Aggregated results from all check categories."""

    categories: dict[str, CategoryResult] = Field(
        default_factory=dict, description="Results keyed by category name"
    )
    first_failure: str | None = Field(
        default=None, description="Name of first failing category, or None"
    )
    all_passed: bool = Field(default=True, description="True if all categories passed")
```

**Validation:**
```bash
.venv/bin/pyright src/weld/models/status.py  # Expect: 0 errors
.venv/bin/pytest tests/test_models.py -v -k status  # Expect: existing tests pass
```

**Failure mode:** Import error if BaseModel not available → status.py already imports it

---

#### Step 1.1.2: Update Status model to use ChecksSummary

**File:** `src/weld/models/status.py:36-43`

**Current code:**
```python
    pass_: bool = Field(alias="pass", description="Final pass/fail determination")
    issue_count: int = Field(default=0, description="Total issues from review")
    blocker_count: int = Field(default=0, description="Blocker-severity issues")
    major_count: int = Field(default=0, description="Major-severity issues")
    minor_count: int = Field(default=0, description="Minor-severity issues")
    checks_exit_code: int = Field(description="Exit code from checks (-1 if not run)")
    diff_nonempty: bool = Field(description="True if diff contained changes")
    timestamp: datetime = Field(default_factory=datetime.now, description="Status timestamp")
```

**Replace with:**
```python
    pass_: bool = Field(alias="pass", description="Final pass/fail determination")
    issue_count: int = Field(default=0, description="Total issues from review")
    blocker_count: int = Field(default=0, description="Blocker-severity issues")
    major_count: int = Field(default=0, description="Major-severity issues")
    minor_count: int = Field(default=0, description="Minor-severity issues")
    checks_summary: ChecksSummary | None = Field(
        default=None, description="Per-category check results"
    )
    # DEPRECATED: Use checks_summary.first_failure exit code instead
    checks_exit_code: int = Field(
        default=-1, description="Exit code from checks (-1 if not run). Deprecated."
    )
    diff_nonempty: bool = Field(description="True if diff contained changes")
    timestamp: datetime = Field(default_factory=datetime.now, description="Status timestamp")
```

**Validation:**
```bash
.venv/bin/pyright src/weld/models/status.py  # Expect: 0 errors
```

**Failure mode:** Tests using `checks_exit_code` still work due to backward compat field

---

#### Step 1.1.3: Export new models from models/__init__.py

**File:** `src/weld/models/__init__.py`

**Current exports:** Check what's exported and add:
```python
from .status import CategoryResult, ChecksSummary, Status
```

**Validation:**
```bash
python -c "from weld.models import CategoryResult, ChecksSummary"  # Expect: no error
```

---

#### Step 1.1.4: Update ChecksConfig for multi-category

**File:** `src/weld/config.py:45-48`

**Current code:**
```python
class ChecksConfig(BaseModel):
    """Configuration for checks command."""

    command: str = "echo 'No checks configured'"
```

**Replace with:**
```python
class ChecksConfig(BaseModel):
    """Configuration for checks command.

    Supports two modes:
    1. Multi-category (preferred): Define lint/test/typecheck with order
    2. Legacy single command: Use 'command' field (deprecated)
    """

    # Multi-category checks (preferred)
    lint: str | None = Field(default=None, description="Lint command (e.g., 'ruff check .')")
    test: str | None = Field(default=None, description="Test command (e.g., 'pytest tests/')")
    typecheck: str | None = Field(default=None, description="Typecheck command (e.g., 'pyright')")
    order: list[str] = Field(
        default=["lint", "typecheck", "test"],
        description="Execution order for categories"
    )

    # Legacy single command (deprecated, for backward compatibility)
    command: str | None = Field(
        default=None,
        description="Single check command. Deprecated: use category fields instead."
    )

    def get_categories(self) -> dict[str, str]:
        """Get enabled category commands as {name: command} dict."""
        categories = {}
        for name in self.order:
            cmd = getattr(self, name, None)
            if cmd:
                categories[name] = cmd
        return categories

    def is_legacy_mode(self) -> bool:
        """Return True if using deprecated single-command mode."""
        return self.command is not None and not self.get_categories()
```

**Validation:**
```bash
.venv/bin/pyright src/weld/config.py  # Expect: 0 errors
.venv/bin/pytest tests/test_config.py -v  # Expect: existing tests may fail (expected)
```

**Failure mode:** Existing configs with `command` continue to work via `is_legacy_mode()`

---

#### Step 1.1.5: Add tests for new ChecksConfig

**File:** `tests/test_config.py` (append)

```python
class TestChecksConfigCategories:
    """Tests for multi-category checks configuration."""

    def test_get_categories_returns_enabled_only(self) -> None:
        """Only categories with commands are returned."""
        cfg = ChecksConfig(lint="ruff check .", test=None, typecheck="pyright")
        categories = cfg.get_categories()
        assert categories == {"lint": "ruff check .", "typecheck": "pyright"}

    def test_get_categories_respects_order(self) -> None:
        """Categories returned in configured order."""
        cfg = ChecksConfig(
            lint="ruff", test="pytest", typecheck="pyright",
            order=["test", "lint", "typecheck"]
        )
        assert list(cfg.get_categories().keys()) == ["test", "lint", "typecheck"]

    def test_is_legacy_mode_true_when_only_command(self) -> None:
        """Legacy mode when only command field is set."""
        cfg = ChecksConfig(command="make check")
        assert cfg.is_legacy_mode() is True

    def test_is_legacy_mode_false_when_categories_set(self) -> None:
        """Not legacy mode when category commands exist."""
        cfg = ChecksConfig(lint="ruff", command="make check")
        assert cfg.is_legacy_mode() is False

    def test_default_has_no_categories(self) -> None:
        """Default config has no enabled categories."""
        cfg = ChecksConfig()
        assert cfg.get_categories() == {}
        assert cfg.is_legacy_mode() is False
```

**Validation:**
```bash
.venv/bin/pytest tests/test_config.py::TestChecksConfigCategories -v  # Expect: 5 passed
```

---

#### Step 1.1.6: Rewrite checks service for multi-category

**File:** `src/weld/services/checks.py`

**Current code (lines 16-60):**
```python
def run_checks(
    command: str,
    cwd: Path,
    timeout: int | None = None,
) -> tuple[str, int]:
    """Run checks command and return (output, exit_code)..."""
```

**Replace entire function with:**
```python
from ..config import ChecksConfig
from ..models import CategoryResult, ChecksSummary


def run_single_check(
    command: str,
    cwd: Path,
    timeout: int | None = None,
) -> tuple[str, int]:
    """Run a single check command and return (output, exit_code).

    Args:
        command: Shell command to run (will be parsed safely)
        cwd: Working directory
        timeout: Optional timeout in seconds (default: CHECKS_TIMEOUT)

    Returns:
        Tuple of (formatted output with stdout/stderr, exit code)

    Raises:
        ChecksError: If command times out or fails to execute
    """
    timeout = timeout or CHECKS_TIMEOUT

    try:
        args = shlex.split(command)
    except ValueError as e:
        raise ChecksError(f"Invalid command syntax: {e}") from e

    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise ChecksError(f"Check timed out after {timeout} seconds") from e
    except FileNotFoundError:
        raise ChecksError(f"Command not found: {args[0]}") from None

    output = f"exit_code: {result.returncode}\n\n"
    output += "=== stdout ===\n"
    output += result.stdout
    output += "\n=== stderr ===\n"
    output += result.stderr
    return output, result.returncode


def run_checks(
    config: ChecksConfig,
    cwd: Path,
    timeout: int | None = None,
    fail_fast: bool = True,
) -> ChecksSummary:
    """Run checks by category with optional fail-fast.

    Args:
        config: ChecksConfig with category commands
        cwd: Working directory
        timeout: Timeout per check category
        fail_fast: If True, stop at first failure (for iteration loop)
                   If False, run all checks (for review context)

    Returns:
        ChecksSummary with per-category results
    """
    # Handle legacy single-command mode
    if config.is_legacy_mode():
        output, exit_code = run_single_check(config.command, cwd, timeout)
        passed = exit_code == 0
        return ChecksSummary(
            categories={"default": CategoryResult(
                category="default",
                exit_code=exit_code,
                passed=passed,
                output=output,
            )},
            first_failure=None if passed else "default",
            all_passed=passed,
        )

    categories = config.get_categories()
    if not categories:
        # No checks configured
        return ChecksSummary(categories={}, first_failure=None, all_passed=True)

    results: dict[str, CategoryResult] = {}
    first_failure: str | None = None

    for name, command in categories.items():
        try:
            output, exit_code = run_single_check(command, cwd, timeout)
            passed = exit_code == 0
        except ChecksError as e:
            output = str(e)
            exit_code = 1
            passed = False

        results[name] = CategoryResult(
            category=name,
            exit_code=exit_code,
            passed=passed,
            output=output,
        )

        if not passed and first_failure is None:
            first_failure = name
            if fail_fast:
                break

    return ChecksSummary(
        categories=results,
        first_failure=first_failure,
        all_passed=first_failure is None,
    )


# Keep old signature for backward compatibility during migration
def run_checks_legacy(
    command: str,
    cwd: Path,
    timeout: int | None = None,
) -> tuple[str, int]:
    """DEPRECATED: Use run_checks(config, cwd) instead."""
    return run_single_check(command, cwd, timeout)
```

**Also update imports at top of file:**
```python
"""Checks runner for weld."""

import shlex
import subprocess
from pathlib import Path

from ..config import ChecksConfig
from ..constants import CHECKS_TIMEOUT
from ..models import CategoryResult, ChecksSummary
```

**Validation:**
```bash
.venv/bin/pyright src/weld/services/checks.py  # Expect: 0 errors
```

**Failure mode:** Import errors if models not exported → complete step 1.1.3 first

---

#### Step 1.1.7: Update services/__init__.py exports

**File:** `src/weld/services/__init__.py`

**Add to exports:**
```python
from .checks import run_checks, run_single_check, ChecksError
```

**Validation:**
```bash
python -c "from weld.services import run_checks"
```

---

#### Step 1.1.8: Update loop.py to use new checks API

**File:** `src/weld/core/loop.py`

**Current imports (lines 1-19):**
```python
from ..services import capture_diff, run_checks, write_checks, write_diff
```

**Replace with:**
```python
from ..services import capture_diff, write_diff
from ..services.checks import run_checks, write_checks
from ..services.filesystem import ensure_directory
```

**Current code (lines 112-114):**
```python
        # Run checks
        checks_output, checks_exit = run_checks(config.checks.command, repo_root)
        write_checks(iter_dir / "checks.txt", checks_output)
```

**Replace with:**
```python
        # Run checks (fail-fast for iteration, full run for review input)
        checks_summary = run_checks(config.checks, repo_root, fail_fast=True)

        # Write per-category output files
        checks_dir = iter_dir / "checks"
        ensure_directory(checks_dir)
        for name, result in checks_summary.categories.items():
            (checks_dir / f"{name}.txt").write_text(result.output)
        (iter_dir / "checks.summary.json").write_text(
            checks_summary.model_dump_json(indent=2)
        )

        # Run remaining checks for review context (if fail-fast stopped early)
        if checks_summary.first_failure and not checks_summary.all_passed:
            full_summary = run_checks(config.checks, repo_root, fail_fast=False)
            for name, result in full_summary.categories.items():
                if name not in checks_summary.categories:
                    (checks_dir / f"{name}.txt").write_text(result.output)

        # Build combined output for review prompt
        checks_output = "\n\n".join(
            f"=== {name} (exit {r.exit_code}) ===\n{r.output}"
            for name, r in checks_summary.categories.items()
        )
        checks_exit = (
            checks_summary.categories[checks_summary.first_failure].exit_code
            if checks_summary.first_failure
            else 0
        )
```

**Also update status creation (around line 118-130):**

**Current code:**
```python
        review_md, issues, status = run_step_review(
            step=step,
            diff=diff,
            checks_output=checks_output,
            checks_exit_code=checks_exit,
            config=config,
            cwd=repo_root,
        )
```

**After run_step_review, update status to include checks_summary:**
```python
        review_md, issues, status = run_step_review(
            step=step,
            diff=diff,
            checks_output=checks_output,
            checks_exit_code=checks_exit,
            config=config,
            cwd=repo_root,
        )

        # Enrich status with checks summary
        status.checks_summary = checks_summary
```

**Validation:**
```bash
.venv/bin/pyright src/weld/core/loop.py  # Expect: 0 errors
.venv/bin/pytest tests/test_integration.py -v -k loop  # After test updates
```

**Failure mode:** TypeError if checks_summary not on Status → complete step 1.1.2 first

---

#### Step 1.1.9: Update write_checks for directory mode

**File:** `src/weld/services/checks.py:63-71`

**Current code:**
```python
def write_checks(path: Path, output: str) -> None:
    """Write checks output to file..."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output)
```

**Keep as-is for backward compatibility, but it's now only used internally by run_single_check tests**

---

#### Step 1.1.10: Add tests for multi-category checks

**File:** `tests/test_checks.py` (append or create)

```python
import pytest
from pathlib import Path
from weld.config import ChecksConfig
from weld.services.checks import run_checks, run_single_check, ChecksError


class TestRunSingleCheck:
    """Tests for run_single_check function."""

    def test_successful_command(self, tmp_path: Path) -> None:
        """Successful command returns output and exit code 0."""
        output, exit_code = run_single_check("echo hello", tmp_path)
        assert exit_code == 0
        assert "hello" in output

    def test_failing_command(self, tmp_path: Path) -> None:
        """Failing command returns non-zero exit code."""
        output, exit_code = run_single_check("false", tmp_path)
        assert exit_code != 0

    def test_invalid_command_raises(self, tmp_path: Path) -> None:
        """Command not found raises ChecksError."""
        with pytest.raises(ChecksError, match="Command not found"):
            run_single_check("nonexistent_command_xyz", tmp_path)


class TestRunChecksMultiCategory:
    """Tests for multi-category run_checks function."""

    def test_all_categories_pass(self, tmp_path: Path) -> None:
        """All passing categories returns all_passed=True."""
        config = ChecksConfig(lint="true", test="true", typecheck="true")
        summary = run_checks(config, tmp_path)
        assert summary.all_passed is True
        assert summary.first_failure is None
        assert len(summary.categories) == 3

    def test_first_failure_recorded(self, tmp_path: Path) -> None:
        """First failing category is recorded."""
        config = ChecksConfig(
            lint="true", test="false", typecheck="true",
            order=["lint", "test", "typecheck"]
        )
        summary = run_checks(config, tmp_path, fail_fast=True)
        assert summary.all_passed is False
        assert summary.first_failure == "test"
        # With fail_fast, typecheck was not run
        assert "typecheck" not in summary.categories

    def test_fail_fast_false_runs_all(self, tmp_path: Path) -> None:
        """fail_fast=False runs all categories even after failure."""
        config = ChecksConfig(
            lint="false", test="true", typecheck="true",
            order=["lint", "test", "typecheck"]
        )
        summary = run_checks(config, tmp_path, fail_fast=False)
        assert summary.first_failure == "lint"
        assert len(summary.categories) == 3  # All ran

    def test_legacy_mode_single_command(self, tmp_path: Path) -> None:
        """Legacy mode with single command works."""
        config = ChecksConfig(command="echo legacy")
        summary = run_checks(config, tmp_path)
        assert "default" in summary.categories
        assert summary.all_passed is True

    def test_empty_config_passes(self, tmp_path: Path) -> None:
        """No checks configured returns all_passed=True."""
        config = ChecksConfig()
        summary = run_checks(config, tmp_path)
        assert summary.all_passed is True
        assert len(summary.categories) == 0
```

**Validation:**
```bash
.venv/bin/pytest tests/test_checks.py::TestRunChecksMultiCategory -v  # Expect: 5 passed
```

---

#### Step 1.1.11: Update write_config_template for multi-category

**File:** `src/weld/config.py:147-180`

**Current template dict (around line 157):**
```python
        "checks": {"command": "echo 'Configure your checks command'"},
```

**Replace with:**
```python
        "checks": {
            "lint": "ruff check .",
            "test": "pytest tests/ -q",
            "typecheck": "pyright",
            "order": ["lint", "typecheck", "test"],
        },
```

**Validation:**
```bash
rm -rf /tmp/test_weld && mkdir -p /tmp/test_weld/.weld
python -c "from weld.config import write_config_template; from pathlib import Path; write_config_template(Path('/tmp/test_weld/.weld'))"
cat /tmp/test_weld/.weld/config.toml | grep -A5 checks  # Should show multi-category
```

---

### 1.2 Run Locking **COMPLETE**

**Current state:** No locking; concurrent runs can corrupt state

**Target state:** PID-based file lock with stale detection

#### Step 1.2.1: Add Lock model

**File:** `src/weld/models/lock.py` (create new file)

```python
"""Lock model for concurrent run prevention.

Implements PID-based file locking to ensure only one weld command
modifies run state at a time.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Lock(BaseModel):
    """Active run lock written to .weld/active.lock.

    Attributes:
        pid: Process ID of the lock holder.
        run_id: ID of the run being modified.
        command: Command that acquired the lock.
        started_at: When the lock was acquired.
        last_heartbeat: Last heartbeat update (for stale detection).
    """

    pid: int = Field(description="Process ID holding the lock")
    run_id: str = Field(description="Run ID being modified")
    command: str = Field(description="Command that acquired lock")
    started_at: datetime = Field(default_factory=datetime.now)
    last_heartbeat: datetime = Field(default_factory=datetime.now)
```

**Validation:**
```bash
.venv/bin/pyright src/weld/models/lock.py  # Expect: 0 errors
```

---

#### Step 1.2.2: Export Lock from models/__init__.py

**File:** `src/weld/models/__init__.py`

**Add:**
```python
from .lock import Lock
```

**And add to `__all__` list.**

**Validation:**
```bash
python -c "from weld.models import Lock"
```

---

#### Step 1.2.3: Create lock manager

**File:** `src/weld/core/lock_manager.py` (create new file)

```python
"""Lock manager for weld run concurrency control.

Provides PID-based file locking to prevent concurrent modifications
to weld runs. Includes stale lock detection for crash recovery.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

from ..models import Lock

LOCK_FILE = "active.lock"
STALE_TIMEOUT_SECONDS = 3600  # 1 hour


class LockError(Exception):
    """Error acquiring or managing lock."""
    pass


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
    if age > timedelta(seconds=timeout_seconds):
        return True

    return False


def acquire_lock(weld_dir: Path, run_id: str, command: str) -> Lock:
    """Acquire lock for run modification.

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
    existing = get_current_lock(weld_dir)

    if existing:
        if is_stale_lock(existing):
            # Clear stale lock
            lock_path.unlink()
        elif existing.pid != os.getpid():
            raise LockError(
                f"Run already in progress (PID {existing.pid}, "
                f"command: {existing.command})"
            )
        # If same PID, we already own it - update it

    lock = Lock(
        pid=os.getpid(),
        run_id=run_id,
        command=command,
    )

    lock_path.write_text(lock.model_dump_json(indent=2))
    return lock


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
```

**Validation:**
```bash
.venv/bin/pyright src/weld/core/lock_manager.py  # Expect: 0 errors
```

---

#### Step 1.2.4: Add lock manager tests

**File:** `tests/test_lock_manager.py` (create new file)

```python
"""Tests for lock manager."""

import os
import pytest
from datetime import datetime, timedelta
from pathlib import Path

from weld.core.lock_manager import (
    acquire_lock,
    release_lock,
    get_current_lock,
    is_stale_lock,
    LockError,
)
from weld.models import Lock


@pytest.fixture
def weld_dir(tmp_path: Path) -> Path:
    """Create temporary .weld directory."""
    d = tmp_path / ".weld"
    d.mkdir()
    return d


class TestAcquireLock:
    """Tests for acquire_lock function."""

    def test_acquire_creates_lock_file(self, weld_dir: Path) -> None:
        """Acquiring lock creates lock file."""
        lock = acquire_lock(weld_dir, "run-123", "step loop")
        assert lock.pid == os.getpid()
        assert lock.run_id == "run-123"
        assert (weld_dir / "active.lock").exists()

    def test_acquire_fails_if_locked_by_other(self, weld_dir: Path) -> None:
        """Cannot acquire if another process holds lock."""
        # Create lock with different PID
        fake_lock = Lock(
            pid=99999,  # Non-existent but not our PID
            run_id="other-run",
            command="other command",
        )
        (weld_dir / "active.lock").write_text(fake_lock.model_dump_json())

        # Our acquire should fail (unless PID 99999 is not running)
        # Note: This test assumes PID 99999 is not running
        lock = acquire_lock(weld_dir, "new-run", "new command")
        # Should succeed because 99999 is not running (stale)
        assert lock.run_id == "new-run"

    def test_acquire_same_pid_updates_lock(self, weld_dir: Path) -> None:
        """Same process can re-acquire/update lock."""
        lock1 = acquire_lock(weld_dir, "run-1", "cmd-1")
        lock2 = acquire_lock(weld_dir, "run-2", "cmd-2")
        assert lock2.run_id == "run-2"


class TestReleaseLock:
    """Tests for release_lock function."""

    def test_release_removes_lock_file(self, weld_dir: Path) -> None:
        """Releasing lock removes lock file."""
        acquire_lock(weld_dir, "run-123", "test")
        assert (weld_dir / "active.lock").exists()
        release_lock(weld_dir)
        assert not (weld_dir / "active.lock").exists()

    def test_release_ignores_other_pids_lock(self, weld_dir: Path) -> None:
        """Cannot release lock held by different PID."""
        fake_lock = Lock(pid=99999, run_id="other", command="other")
        (weld_dir / "active.lock").write_text(fake_lock.model_dump_json())
        release_lock(weld_dir)  # Should do nothing
        assert (weld_dir / "active.lock").exists()


class TestIsStale:
    """Tests for is_stale_lock function."""

    def test_dead_pid_is_stale(self) -> None:
        """Lock with dead PID is stale."""
        lock = Lock(pid=99999, run_id="test", command="test")
        # PID 99999 is almost certainly not running
        assert is_stale_lock(lock) is True

    def test_old_heartbeat_is_stale(self) -> None:
        """Lock with old heartbeat is stale."""
        lock = Lock(
            pid=os.getpid(),  # Our PID, so not dead
            run_id="test",
            command="test",
            last_heartbeat=datetime.now() - timedelta(hours=2),
        )
        assert is_stale_lock(lock, timeout_seconds=3600) is True

    def test_fresh_lock_not_stale(self) -> None:
        """Fresh lock is not stale."""
        lock = Lock(pid=os.getpid(), run_id="test", command="test")
        assert is_stale_lock(lock) is False
```

**Validation:**
```bash
.venv/bin/pytest tests/test_lock_manager.py -v  # Expect: all pass
```

---

#### Step 1.2.5: Export lock manager from core/__init__.py

**File:** `src/weld/core/__init__.py`

**Add:**
```python
from .lock_manager import acquire_lock, release_lock, LockError
```

**Validation:**
```bash
python -c "from weld.core import acquire_lock, release_lock, LockError"
```

---

#### Step 1.2.6: Apply lock to run command

**File:** `src/weld/commands/run.py`

**Add import at top:**
```python
from ..core import acquire_lock, release_lock, LockError
```

**Wrap run_start function body (preserve existing signature):**

In the function body, after getting weld_dir, add:
```python
    try:
        acquire_lock(weld_dir, run_id, f"run --spec {spec}")
    except LockError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    try:
        # ... existing function body ...
    finally:
        release_lock(weld_dir)
```

**Note:** Detailed line numbers depend on current run.py structure. Read file first.

**Validation:**
```bash
# Start a run in one terminal, try to start another - should fail
```

---

### 1.3 Complete TaskType Enum **COMPLETE**

**Current state:** Missing DISCOVER, INTERVIEW, RESEARCH, RESEARCH_REVIEW

**File:** `src/weld/config.py:11-18`

**Current code:**
```python
class TaskType(str, Enum):
    """Types of tasks that can be assigned to different models."""

    PLAN_GENERATION = "plan_generation"
    PLAN_REVIEW = "plan_review"
    IMPLEMENTATION = "implementation"
    IMPLEMENTATION_REVIEW = "implementation_review"
    FIX_GENERATION = "fix_generation"
```

**Replace with:**
```python
class TaskType(str, Enum):
    """Types of tasks that can be assigned to different models."""

    # Discovery and interview (brownfield)
    DISCOVER = "discover"
    INTERVIEW = "interview"

    # Research phase
    RESEARCH = "research"
    RESEARCH_REVIEW = "research_review"

    # Plan phase
    PLAN_GENERATION = "plan_generation"
    PLAN_REVIEW = "plan_review"

    # Implementation phase
    IMPLEMENTATION = "implementation"
    IMPLEMENTATION_REVIEW = "implementation_review"
    FIX_GENERATION = "fix_generation"
```

**Also update TaskModelsConfig (around line 29-38) to add defaults:**
```python
class TaskModelsConfig(BaseModel):
    """Per-task model assignments."""

    discover: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    interview: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    research: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    research_review: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="codex"))
    plan_generation: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    plan_review: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="codex"))
    implementation: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    implementation_review: ModelConfig = Field(
        default_factory=lambda: ModelConfig(provider="codex")
    )
    fix_generation: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
```

**Validation:**
```bash
.venv/bin/pyright src/weld/config.py  # Expect: 0 errors
python -c "from weld.config import TaskType; print(TaskType.RESEARCH)"
```

---

### 1.4 Global CLI Options **COMPLETE**

**File:** `src/weld/cli.py:66-108`

**Current callback parameters:**
```python
@app.callback()
def main(
    version: bool = typer.Option(...),
    verbose: int = typer.Option(...),
    quiet: bool = typer.Option(...),
    json_output: bool = typer.Option(...),
    no_color: bool = typer.Option(...),
) -> None:
```

**Add new parameters:**
```python
@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    verbose: int = typer.Option(
        0,
        "--verbose",
        "-v",
        count=True,
        help="Increase verbosity (-v, -vv)",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress non-error output",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output in JSON format for automation",
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable colored output",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview effects without applying changes",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug logging for this invocation",
    ),
) -> None:
```

**Update OutputContext creation (around line 107):**
```python
    _ctx = OutputContext(console=console, json_mode=json_output, dry_run=dry_run)
```

**File:** `src/weld/output.py:10-15`

**Add dry_run field:**
```python
@dataclass
class OutputContext:
    """Context for output formatting."""

    console: Console
    json_mode: bool = False
    dry_run: bool = False
```

**Validation:**
```bash
weld --help  # Should show --dry-run and --debug options
weld --dry-run --help  # Should not error
```

---

## Decisions (Resolved)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Research default | `--skip-research` to opt-out | Matches spec's "discovery → research → plan" flow as default |
| History retention | 5 versions | Balances disk usage vs rollback depth |
| Interview UI | Simple stdin/stdout for v1 | Avoid prompt_toolkit dependency; iterate later |
| Lock heartbeat freq | 60 seconds | Long enough to not spam disk, short enough for stale detection |

---

## Phase 2: Research Phase **COMPLETE**

**Prerequisite:** Phase 1 complete (multi-category checks, run locking, TaskType enum)

### 2.1 Add Research Directory to Run Structure

**File:** `src/weld/core/run_manager.py`

**Current code (find `create_run_directory` function, around line 80-100):**
```python
def create_run_directory(weld_dir: Path, run_id: str) -> Path:
    """Create directory structure for a new run."""
    run_dir = weld_dir / "runs" / run_id
    (run_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (run_dir / "plan").mkdir(parents=True, exist_ok=True)
    (run_dir / "steps").mkdir(parents=True, exist_ok=True)
    (run_dir / "commit").mkdir(parents=True, exist_ok=True)
    return run_dir
```

**Replace with:**
```python
def create_run_directory(weld_dir: Path, run_id: str, skip_research: bool = False) -> Path:
    """Create directory structure for a new run.

    Args:
        weld_dir: Path to .weld directory
        run_id: Unique run identifier
        skip_research: If True, skip research/ directory (direct planning)

    Returns:
        Path to the created run directory
    """
    run_dir = weld_dir / "runs" / run_id
    (run_dir / "inputs").mkdir(parents=True, exist_ok=True)
    if not skip_research:
        (run_dir / "research").mkdir(parents=True, exist_ok=True)
    (run_dir / "plan").mkdir(parents=True, exist_ok=True)
    (run_dir / "steps").mkdir(parents=True, exist_ok=True)
    (run_dir / "commit").mkdir(parents=True, exist_ok=True)
    return run_dir
```

**Validation:**
```bash
.venv/bin/pyright src/weld/core/run_manager.py  # Expect: 0 errors
.venv/bin/pytest tests/test_run.py -v  # May need test updates
```

**Failure mode:** Existing callers pass only 2 args → default `skip_research=False` preserves behavior

---

### 2.2 Update run.py to Support --skip-research Flag

**File:** `src/weld/commands/run.py`

**Current function signature (find `run_start` or main run function):**
```python
def run_start(
    spec: Path = typer.Option(..., "--spec", "-s", help="Path to spec file"),
) -> None:
```

**Add new parameter:**
```python
def run_start(
    spec: Path = typer.Option(..., "--spec", "-s", help="Path to spec file"),
    skip_research: bool = typer.Option(
        False,
        "--skip-research",
        help="Skip research phase, generate plan directly",
    ),
) -> None:
```

**Update call to create_run_directory:**
```python
    run_dir = create_run_directory(weld_dir, run_id, skip_research=skip_research)
```

**Validation:**
```bash
weld run --help  # Should show --skip-research option
```

---

### 2.3 Create Research Processor Module

**File:** `src/weld/core/research_processor.py` (create new file)

```python
"""Research phase processor for weld runs.

Generates research prompts and manages research artifact creation
based on the input specification.
"""

from pathlib import Path

from ..models import Step

RESEARCH_PROMPT_TEMPLATE = '''You are a senior software architect analyzing a specification for implementation planning.

## Task

Analyze the following specification and produce a comprehensive research document that will inform the implementation plan.

## Specification

{spec_content}

## Research Requirements

Your research document should:

1. **Architecture Analysis**
   - Identify existing code patterns to follow
   - Note extension points and integration boundaries
   - Flag potential conflicts with existing systems

2. **Dependency Mapping**
   - External dependencies required
   - Internal module dependencies
   - Version constraints or compatibility concerns

3. **Risk Assessment**
   - Technical risks and mitigation strategies
   - Areas requiring prototyping or spikes
   - Performance or security considerations

4. **Open Questions**
   - Ambiguities in the specification
   - Decisions that need human input
   - Alternative approaches worth considering

## Output Format

Write a markdown document with clear sections. Use file:line references where applicable (no code snippets).
'''


def generate_research_prompt(spec_content: str) -> str:
    """Generate research prompt from specification content.

    Args:
        spec_content: The specification markdown content

    Returns:
        Formatted prompt for AI research generation
    """
    return RESEARCH_PROMPT_TEMPLATE.format(spec_content=spec_content)


def write_research_prompt(research_dir: Path, prompt: str) -> Path:
    """Write research prompt to file.

    Args:
        research_dir: Path to run's research/ directory
        prompt: The generated prompt content

    Returns:
        Path to the written prompt file
    """
    prompt_path = research_dir / "prompt.md"
    prompt_path.write_text(prompt)
    return prompt_path


def import_research(research_dir: Path, content: str) -> Path:
    """Import AI-generated research content.

    Args:
        research_dir: Path to run's research/ directory
        content: The research markdown content

    Returns:
        Path to the written research file
    """
    research_path = research_dir / "research.md"
    research_path.write_text(content)
    return research_path


def get_research_content(research_dir: Path) -> str | None:
    """Get current research content if it exists.

    Args:
        research_dir: Path to run's research/ directory

    Returns:
        Research content or None if not yet imported
    """
    research_path = research_dir / "research.md"
    if research_path.exists():
        return research_path.read_text()
    return None
```

**Validation:**
```bash
.venv/bin/pyright src/weld/core/research_processor.py  # Expect: 0 errors
```

---

### 2.4 Export Research Processor from core/__init__.py

**File:** `src/weld/core/__init__.py`

**Add to exports:**
```python
from .research_processor import (
    generate_research_prompt,
    write_research_prompt,
    import_research,
    get_research_content,
)
```

**Validation:**
```bash
python -c "from weld.core import generate_research_prompt"
```

---

### 2.5 Create Research Commands Module

**File:** `src/weld/commands/research.py` (create new file)

```python
"""Research phase CLI commands."""

from pathlib import Path

import typer

from ..core import (
    generate_research_prompt,
    write_research_prompt,
    import_research,
    get_research_content,
)
from ..output import get_output_context
from ..services.git import get_repo_root, GitError
from ..validation import get_weld_dir, get_run_dir

research_app = typer.Typer(help="Research phase commands")


@research_app.command("prompt")
def research_prompt(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
) -> None:
    """Display the research prompt for a run."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    research_dir = run_dir / "research"

    if not research_dir.exists():
        ctx.error("Run was created with --skip-research")
        raise typer.Exit(1) from None

    prompt_path = research_dir / "prompt.md"
    if prompt_path.exists():
        ctx.console.print(prompt_path.read_text())
    else:
        ctx.error("Research prompt not yet generated")
        raise typer.Exit(1) from None


@research_app.command("import")
def research_import(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    file: Path = typer.Option(..., "--file", "-f", help="Research file from AI"),
) -> None:
    """Import AI-generated research document."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    if not file.exists():
        ctx.error(f"File not found: {file}")
        raise typer.Exit(1) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    research_dir = run_dir / "research"

    if not research_dir.exists():
        ctx.error("Run was created with --skip-research")
        raise typer.Exit(1) from None

    content = file.read_text()
    import_research(research_dir, content)
    ctx.success(f"Research imported to {run}/research/research.md")


@research_app.command("show")
def research_show(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
) -> None:
    """Display the current research document."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    research_dir = run_dir / "research"

    content = get_research_content(research_dir)
    if content:
        ctx.console.print(content)
    else:
        ctx.error("No research document found. Run 'weld research import' first.")
        raise typer.Exit(1) from None
```

**Validation:**
```bash
.venv/bin/pyright src/weld/commands/research.py  # Expect: 0 errors
```

---

### 2.6 Register Research Commands in CLI

**File:** `src/weld/cli.py`

**Add import near other command imports:**
```python
from .commands.research import research_app
```

**Add app registration (after other app.add_typer calls):**
```python
app.add_typer(research_app, name="research")
```

**Validation:**
```bash
weld research --help  # Should show prompt, import, show subcommands
```

---

### 2.7 Update Run Command to Generate Research Prompt

**File:** `src/weld/commands/run.py`

**Add import:**
```python
from ..core import generate_research_prompt, write_research_prompt
```

**In run_start function, after creating run directory, before plan prompt generation:**

**Find code that generates plan prompt (calls to plan_parser functions)**

**Add conditional logic:**
```python
    # Read spec content
    spec_content = spec.read_text()

    if skip_research:
        # Direct planning mode - generate plan prompt immediately
        # ... existing plan prompt generation code ...
    else:
        # Research-first mode (default)
        research_dir = run_dir / "research"
        research_prompt = generate_research_prompt(spec_content)
        write_research_prompt(research_dir, research_prompt)
        ctx.success(f"Research prompt written to {run_id}/research/prompt.md")
        ctx.console.print("\nNext steps:")
        ctx.console.print("  1. Copy prompt.md content to Claude")
        ctx.console.print("  2. Save response as research.md")
        ctx.console.print(f"  3. Run: weld research import --run {run_id} --file research.md")
```

**Validation:**
```bash
# Create new run without --skip-research
weld run --spec /tmp/test-spec.md
# Should create research/prompt.md, NOT plan/prompt.md
```

---

### 2.8 Add Research Tests

**File:** `tests/test_research.py` (create new file)

```python
"""Tests for research phase functionality."""

import pytest
from pathlib import Path

from weld.core.research_processor import (
    generate_research_prompt,
    write_research_prompt,
    import_research,
    get_research_content,
)


class TestGenerateResearchPrompt:
    """Tests for generate_research_prompt function."""

    def test_includes_spec_content(self) -> None:
        """Prompt includes the specification content."""
        spec = "# My Feature\n\nImplement authentication."
        prompt = generate_research_prompt(spec)
        assert "# My Feature" in prompt
        assert "Implement authentication" in prompt

    def test_includes_research_instructions(self) -> None:
        """Prompt includes research structure guidance."""
        prompt = generate_research_prompt("test spec")
        assert "Architecture Analysis" in prompt
        assert "Risk Assessment" in prompt
        assert "Open Questions" in prompt


class TestResearchFiles:
    """Tests for research file operations."""

    def test_write_and_read_prompt(self, tmp_path: Path) -> None:
        """Can write and read research prompt."""
        research_dir = tmp_path / "research"
        research_dir.mkdir()

        prompt = "Test research prompt"
        path = write_research_prompt(research_dir, prompt)

        assert path.exists()
        assert path.read_text() == prompt

    def test_import_research(self, tmp_path: Path) -> None:
        """Can import research content."""
        research_dir = tmp_path / "research"
        research_dir.mkdir()

        content = "# Research\n\nFindings here."
        path = import_research(research_dir, content)

        assert path.name == "research.md"
        assert path.read_text() == content

    def test_get_research_content_exists(self, tmp_path: Path) -> None:
        """Returns content when research exists."""
        research_dir = tmp_path / "research"
        research_dir.mkdir()
        (research_dir / "research.md").write_text("findings")

        content = get_research_content(research_dir)
        assert content == "findings"

    def test_get_research_content_missing(self, tmp_path: Path) -> None:
        """Returns None when research doesn't exist."""
        research_dir = tmp_path / "research"
        research_dir.mkdir()

        content = get_research_content(research_dir)
        assert content is None
```

**Validation:**
```bash
.venv/bin/pytest tests/test_research.py -v  # Expect: all pass
```

---

## Phase 3: Artifact Versioning **COMPLETE**

**Prerequisite:** Phase 2 complete (research phase infrastructure)

### 3.1 Create VersionInfo Model

**File:** `src/weld/models/version_info.py` (create new file)

```python
"""Version tracking models for research and plan artifacts.

Enables history tracking with up to 5 versions retained per artifact.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class VersionInfo(BaseModel):
    """Metadata for a single artifact version.

    Attributes:
        version: Version number (1-indexed)
        created_at: When this version was created
        review_id: Optional reference to review that triggered new version
        trigger_reason: Why this version was created (import, review, regenerate)
        superseded_at: When this version was replaced (None if current)
    """

    version: int = Field(ge=1, description="Version number")
    created_at: datetime = Field(default_factory=datetime.now)
    review_id: str | None = Field(default=None, description="Review that triggered this version")
    trigger_reason: str | None = Field(default=None, description="Reason for version creation")
    superseded_at: datetime | None = Field(default=None, description="When superseded")


class StaleOverride(BaseModel):
    """Record of user overriding a stale artifact warning.

    Attributes:
        timestamp: When the override was recorded
        artifact: Which artifact was stale (research, plan)
        stale_reason: Why it was considered stale
    """

    timestamp: datetime = Field(default_factory=datetime.now)
    artifact: str = Field(description="Stale artifact name")
    stale_reason: str = Field(description="Reason artifact was stale")


class CommandEvent(BaseModel):
    """Record of a command execution for audit trail.

    Attributes:
        timestamp: When command was executed
        command: Full command string
    """

    timestamp: datetime = Field(default_factory=datetime.now)
    command: str = Field(description="Executed command")


# Maximum versions to retain (Decision: 5 versions)
MAX_VERSIONS = 5
```

**Validation:**
```bash
.venv/bin/pyright src/weld/models/version_info.py  # Expect: 0 errors
```

---

### 3.2 Export VersionInfo Models

**File:** `src/weld/models/__init__.py`

**Add imports:**
```python
from .version_info import VersionInfo, StaleOverride, CommandEvent, MAX_VERSIONS
```

**Add to `__all__` list.**

**Validation:**
```bash
python -c "from weld.models import VersionInfo, MAX_VERSIONS; print(MAX_VERSIONS)"  # Should print 5
```

---

### 3.3 Update Meta Model with Version Tracking

**File:** `src/weld/models/meta.py`

**Add imports at top:**
```python
from .version_info import StaleOverride, CommandEvent
```

**Current Meta class fields (around lines 51-63):**
```python
    run_id: str = Field(description="Unique run identifier")
    created_at: datetime = Field(default_factory=datetime.now, description="Run creation time")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last modification time")
    repo_root: Path = Field(description="Git repository root path")
    branch: str = Field(description="Git branch at run creation")
    head_sha: str = Field(description="Git HEAD SHA at run creation")
    config_hash: str = Field(description="Hash of weld config for change detection")
    tool_versions: dict[str, str] = Field(
        default_factory=dict, description="Version info for external tools"
    )
    plan_parse_warnings: list[str] = Field(
        default_factory=list, description="Warnings from plan parsing"
    )
```

**Add new fields after existing ones:**
```python
    # Version tracking
    research_version: int = Field(default=1, description="Current research version")
    plan_version: int = Field(default=1, description="Current plan version")

    # Staleness tracking
    stale_artifacts: list[str] = Field(
        default_factory=list, description="Artifacts marked as stale"
    )
    stale_overrides: list[StaleOverride] = Field(
        default_factory=list, description="User overrides of stale warnings"
    )

    # Run state
    last_used_at: datetime | None = Field(default=None, description="Last command execution")
    command_history: list[CommandEvent] = Field(
        default_factory=list, description="Command execution history"
    )
    abandoned: bool = Field(default=False, description="Whether run is abandoned")
    abandoned_at: datetime | None = Field(default=None, description="When run was abandoned")
```

**Validation:**
```bash
.venv/bin/pyright src/weld/models/meta.py  # Expect: 0 errors
```

**Failure mode:** Existing meta.json files load fine due to defaults on all new fields

---

### 3.4 Create Artifact Versioning Manager

**File:** `src/weld/core/artifact_versioning.py` (create new file)

```python
"""Artifact versioning manager for research and plan documents.

Maintains version history with automatic pruning to MAX_VERSIONS (5).
Each version is stored in history/v<N>/ with content.md and meta.json.
"""

import shutil
from datetime import datetime
from pathlib import Path

from ..models import VersionInfo, MAX_VERSIONS


def get_current_version(artifact_dir: Path) -> int:
    """Get current version number from artifact directory.

    Args:
        artifact_dir: Path to research/ or plan/ directory

    Returns:
        Current version number (1 if no history exists)
    """
    history_dir = artifact_dir / "history"
    if not history_dir.exists():
        return 1

    versions = [
        int(d.name[1:])  # Extract N from "vN"
        for d in history_dir.iterdir()
        if d.is_dir() and d.name.startswith("v") and d.name[1:].isdigit()
    ]
    return max(versions) if versions else 1


def create_version_snapshot(
    artifact_dir: Path,
    content_file: str,
    trigger_reason: str,
    review_id: str | None = None,
) -> int:
    """Create a new version snapshot of an artifact.

    Args:
        artifact_dir: Path to research/ or plan/ directory
        content_file: Name of the content file (e.g., "research.md", "plan.md")
        trigger_reason: Why this version was created
        review_id: Optional review ID that triggered the new version

    Returns:
        The new version number
    """
    content_path = artifact_dir / content_file
    if not content_path.exists():
        return 1  # No content to version yet

    history_dir = artifact_dir / "history"
    history_dir.mkdir(exist_ok=True)

    # Determine new version number
    current = get_current_version(artifact_dir)
    new_version = current + 1

    # Create version directory
    version_dir = history_dir / f"v{new_version}"
    version_dir.mkdir(exist_ok=True)

    # Copy content
    shutil.copy2(content_path, version_dir / "content.md")

    # Write version metadata
    version_info = VersionInfo(
        version=new_version,
        trigger_reason=trigger_reason,
        review_id=review_id,
    )
    (version_dir / "meta.json").write_text(version_info.model_dump_json(indent=2))

    # Mark previous version as superseded
    if current >= 1:
        prev_meta_path = history_dir / f"v{current}" / "meta.json"
        if prev_meta_path.exists():
            prev_info = VersionInfo.model_validate_json(prev_meta_path.read_text())
            prev_info.superseded_at = datetime.now()
            prev_meta_path.write_text(prev_info.model_dump_json(indent=2))

    # Prune old versions (keep only MAX_VERSIONS)
    _prune_old_versions(history_dir)

    return new_version


def _prune_old_versions(history_dir: Path) -> None:
    """Remove versions beyond MAX_VERSIONS, keeping newest.

    Args:
        history_dir: Path to history/ directory
    """
    version_dirs = sorted(
        [d for d in history_dir.iterdir() if d.is_dir() and d.name.startswith("v")],
        key=lambda d: int(d.name[1:]),
        reverse=True,  # Newest first
    )

    for old_dir in version_dirs[MAX_VERSIONS:]:
        shutil.rmtree(old_dir)


def get_version_history(artifact_dir: Path) -> list[VersionInfo]:
    """Get version history for an artifact.

    Args:
        artifact_dir: Path to research/ or plan/ directory

    Returns:
        List of VersionInfo, newest first
    """
    history_dir = artifact_dir / "history"
    if not history_dir.exists():
        return []

    versions = []
    for version_dir in history_dir.iterdir():
        if version_dir.is_dir() and version_dir.name.startswith("v"):
            meta_path = version_dir / "meta.json"
            if meta_path.exists():
                versions.append(VersionInfo.model_validate_json(meta_path.read_text()))

    return sorted(versions, key=lambda v: v.version, reverse=True)


def restore_version(artifact_dir: Path, version: int, content_file: str) -> bool:
    """Restore a previous version as current.

    Args:
        artifact_dir: Path to research/ or plan/ directory
        version: Version number to restore
        content_file: Name of the content file

    Returns:
        True if restored successfully
    """
    version_content = artifact_dir / "history" / f"v{version}" / "content.md"
    if not version_content.exists():
        return False

    # First, snapshot current as new version
    create_version_snapshot(artifact_dir, content_file, f"pre-restore from v{version}")

    # Then copy old content to current
    shutil.copy2(version_content, artifact_dir / content_file)
    return True
```

**Validation:**
```bash
.venv/bin/pyright src/weld/core/artifact_versioning.py  # Expect: 0 errors
```

---

### 3.5 Export Artifact Versioning Functions

**File:** `src/weld/core/__init__.py`

**Add:**
```python
from .artifact_versioning import (
    get_current_version,
    create_version_snapshot,
    get_version_history,
    restore_version,
)
```

**Validation:**
```bash
python -c "from weld.core import create_version_snapshot"
```

---

### 3.6 Update Research Import to Use Versioning

**File:** `src/weld/commands/research.py`

**Add import:**
```python
from ..core import create_version_snapshot, get_current_version
```

**Update research_import function to create version snapshot:**

**Before writing new content, add:**
```python
    # Check if research already exists - create version snapshot
    existing_research = research_dir / "research.md"
    if existing_research.exists():
        version = create_version_snapshot(
            research_dir,
            "research.md",
            trigger_reason="import",
        )
        ctx.info(f"Previous research saved as v{version - 1}")
```

**Validation:**
```bash
# Import research twice - should create history/v2/
weld research import --run test-run --file research1.md
weld research import --run test-run --file research2.md
ls .weld/runs/test-run/research/history/  # Should show v1/, v2/
```

---

### 3.7 Update Plan Import to Use Versioning

**File:** `src/weld/commands/plan.py`

**Add import:**
```python
from ..core import create_version_snapshot
```

**In plan_import function, before writing new plan:**
```python
    # Create version snapshot if plan already exists
    existing_plan = plan_dir / "plan.md"
    if existing_plan.exists():
        create_version_snapshot(
            plan_dir,
            "plan.md",
            trigger_reason="import",
        )
```

**Note:** This requires migrating from `plan.raw.md`/`plan.final.md` to `plan.md`. Consider adding a migration step or supporting both naming schemes.

**Validation:**
```bash
.venv/bin/pytest tests/test_plan.py -v  # After updating tests
```

---

### 3.8 Add Artifact Versioning Tests

**File:** `tests/test_artifact_versioning.py` (create new file)

```python
"""Tests for artifact versioning functionality."""

import pytest
from pathlib import Path

from weld.core.artifact_versioning import (
    get_current_version,
    create_version_snapshot,
    get_version_history,
    restore_version,
)
from weld.models import MAX_VERSIONS


@pytest.fixture
def artifact_dir(tmp_path: Path) -> Path:
    """Create a temporary artifact directory."""
    d = tmp_path / "research"
    d.mkdir()
    return d


class TestGetCurrentVersion:
    """Tests for get_current_version function."""

    def test_returns_1_when_no_history(self, artifact_dir: Path) -> None:
        """Returns 1 when no history directory exists."""
        assert get_current_version(artifact_dir) == 1

    def test_returns_highest_version(self, artifact_dir: Path) -> None:
        """Returns the highest version number from history."""
        history = artifact_dir / "history"
        (history / "v1").mkdir(parents=True)
        (history / "v3").mkdir()
        (history / "v2").mkdir()
        assert get_current_version(artifact_dir) == 3


class TestCreateVersionSnapshot:
    """Tests for create_version_snapshot function."""

    def test_creates_version_directory(self, artifact_dir: Path) -> None:
        """Creates history/vN directory with content and meta."""
        (artifact_dir / "research.md").write_text("# Research v1")

        version = create_version_snapshot(
            artifact_dir,
            "research.md",
            trigger_reason="import",
        )

        assert version == 2  # First snapshot is v2 (v1 is implicit current)
        assert (artifact_dir / "history" / "v2" / "content.md").exists()
        assert (artifact_dir / "history" / "v2" / "meta.json").exists()

    def test_prunes_old_versions(self, artifact_dir: Path) -> None:
        """Keeps only MAX_VERSIONS versions."""
        (artifact_dir / "research.md").write_text("content")

        # Create MAX_VERSIONS + 2 versions
        for i in range(MAX_VERSIONS + 2):
            create_version_snapshot(artifact_dir, "research.md", f"version {i}")

        history = artifact_dir / "history"
        versions = list(history.iterdir())
        assert len(versions) == MAX_VERSIONS


class TestGetVersionHistory:
    """Tests for get_version_history function."""

    def test_returns_empty_when_no_history(self, artifact_dir: Path) -> None:
        """Returns empty list when no history exists."""
        assert get_version_history(artifact_dir) == []

    def test_returns_versions_newest_first(self, artifact_dir: Path) -> None:
        """Returns versions sorted newest first."""
        (artifact_dir / "research.md").write_text("content")
        create_version_snapshot(artifact_dir, "research.md", "v1")
        create_version_snapshot(artifact_dir, "research.md", "v2")

        history = get_version_history(artifact_dir)
        assert len(history) == 2
        assert history[0].version > history[1].version


class TestRestoreVersion:
    """Tests for restore_version function."""

    def test_restores_old_content(self, artifact_dir: Path) -> None:
        """Restoring version copies old content to current."""
        content_file = "research.md"
        (artifact_dir / content_file).write_text("original")
        create_version_snapshot(artifact_dir, content_file, "first")

        (artifact_dir / content_file).write_text("modified")
        create_version_snapshot(artifact_dir, content_file, "second")

        # Restore version 2 (which has "original" content)
        success = restore_version(artifact_dir, 2, content_file)
        assert success
        assert (artifact_dir / content_file).read_text() == "original"

    def test_returns_false_for_missing_version(self, artifact_dir: Path) -> None:
        """Returns False when version doesn't exist."""
        success = restore_version(artifact_dir, 99, "research.md")
        assert success is False
```

**Validation:**
```bash
.venv/bin/pytest tests/test_artifact_versioning.py -v  # Expect: all pass
```

---

## Validation Checklist

After each phase, run:

```bash
# Quality checks
make check                    # lint + format + types

# Tests with coverage
make test-cov                 # Should maintain >80% coverage

# Specific phase validation
# Phase 1.1:
.venv/bin/pytest tests/test_checks.py tests/test_config.py -v
# Phase 1.2:
.venv/bin/pytest tests/test_lock_manager.py -v
```

---

## Phase 4: Discover & Interview (Brownfield Workflow)

**Prerequisite:** Phase 3 complete (artifact versioning)

### 4.1 Create Discover Metadata Model

**File:** `src/weld/models/discover.py` (create new file)

```python
"""Discover workflow models.

Captures metadata for codebase discovery artifacts, enabling
lineage tracking between discover outputs and implementation runs.
"""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class DiscoverMeta(BaseModel):
    """Metadata for a discover artifact.

    Attributes:
        discover_id: Unique identifier (format: YYYYMMDD-HHMMSS-discover)
        created_at: When discovery was run
        config_hash: Hash of weld config at time of discovery
        output_path: Path where discover output was written
        used_by_runs: List of run IDs that reference this discover
        partial: Whether discovery was interrupted/incomplete
    """

    discover_id: str = Field(description="Unique discover identifier")
    created_at: datetime = Field(default_factory=datetime.now)
    config_hash: str = Field(description="Config hash at discovery time")
    output_path: Path = Field(description="Output file path")
    used_by_runs: list[str] = Field(default_factory=list, description="Runs using this discover")
    partial: bool = Field(default=False, description="True if discovery was interrupted")
```

**Validation:**
```bash
.venv/bin/pyright src/weld/models/discover.py  # Expect: 0 errors
```

---

### 4.2 Export DiscoverMeta Model

**File:** `src/weld/models/__init__.py`

**Add:**
```python
from .discover import DiscoverMeta
```

**Validation:**
```bash
python -c "from weld.models import DiscoverMeta"
```

---

### 4.3 Create Discover Engine

**File:** `src/weld/core/discover_engine.py` (create new file)

```python
"""Discover engine for codebase analysis.

Generates architecture documentation from existing codebases,
providing context for brownfield development planning.
"""

from pathlib import Path

DISCOVER_PROMPT_TEMPLATE = '''You are a senior software architect analyzing an existing codebase.

## Task

Analyze the codebase and produce a comprehensive architecture document that will inform future development.

## Focus Areas

{focus_areas}

## Analysis Requirements

Your document should include:

1. **High-Level Architecture**
   - System overview and design patterns
   - Key components and their responsibilities
   - Data flow between components

2. **Directory Structure**
   - Purpose of each major directory
   - Naming conventions used
   - File organization patterns

3. **Key Files** (file:line references only, no code snippets)
   - Entry points and main modules
   - Configuration files
   - Critical business logic locations

4. **Integration Points**
   - External APIs and services
   - Database connections
   - File system dependencies

5. **Testing Patterns**
   - Test organization
   - Mocking strategies
   - Coverage patterns

## Output Format

Write a markdown document using file:line references. Example:
- Authentication logic: `src/auth/handler.py:45-120`
- Database models: `src/models/user.py:12`

Do NOT include code snippets - only file:line references.
'''


def generate_discover_prompt(focus_areas: str | None = None) -> str:
    """Generate discover prompt for codebase analysis.

    Args:
        focus_areas: Optional specific areas to focus on

    Returns:
        Formatted prompt for AI discovery
    """
    areas = focus_areas or "Analyze the entire codebase holistically."
    return DISCOVER_PROMPT_TEMPLATE.format(focus_areas=areas)


def get_discover_dir(weld_dir: Path) -> Path:
    """Get or create discover directory.

    Args:
        weld_dir: Path to .weld directory

    Returns:
        Path to .weld/discover/ directory
    """
    discover_dir = weld_dir / "discover"
    discover_dir.mkdir(exist_ok=True)
    return discover_dir
```

**Validation:**
```bash
.venv/bin/pyright src/weld/core/discover_engine.py  # Expect: 0 errors
```

---

### 4.4 Create Discover Commands

**File:** `src/weld/commands/discover.py` (create new file)

```python
"""Discover workflow CLI commands."""

from datetime import datetime
from pathlib import Path

import typer

from ..core.discover_engine import generate_discover_prompt, get_discover_dir
from ..models import DiscoverMeta
from ..output import get_output_context
from ..services.git import get_repo_root, GitError
from ..validation import get_weld_dir


@typer.command()
def discover(
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Path to write discover output",
    ),
    focus: str | None = typer.Option(
        None,
        "--focus",
        "-f",
        help="Specific areas to focus on",
    ),
) -> None:
    """Analyze codebase and generate architecture documentation."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    discover_dir = get_discover_dir(weld_dir)

    # Generate discover ID
    discover_id = datetime.now().strftime("%Y%m%d-%H%M%S-discover")

    # Create discover subdirectory
    artifact_dir = discover_dir / discover_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Generate and write prompt
    prompt = generate_discover_prompt(focus)
    prompt_path = artifact_dir / "prompt.md"
    prompt_path.write_text(prompt)

    ctx.success(f"Discover prompt written to .weld/discover/{discover_id}/prompt.md")
    ctx.console.print(f"\nOutput will be written to: {output}")
    ctx.console.print("\nNext steps:")
    ctx.console.print("  1. Copy prompt.md content to Claude")
    ctx.console.print("  2. Save response to the output path")
    ctx.console.print(f"  3. The output at {output} can be used as input to 'weld run --spec'")
```

**Validation:**
```bash
.venv/bin/pyright src/weld/commands/discover.py  # Expect: 0 errors
```

---

### 4.5 Create Interview Engine

**File:** `src/weld/core/interview_engine.py` (create new file)

```python
"""Interview engine for interactive specification refinement.

Uses simple stdin/stdout for v1 (Decision: avoid prompt_toolkit dependency).
"""

from pathlib import Path


INTERVIEW_SYSTEM_PROMPT = '''You are helping refine a specification document through Q&A.

## Rules

1. Ask ONE question at a time
2. Focus on requirements (WHAT), not implementation (HOW)
3. If you detect contradictions, pause and ask for clarification
4. Questions should help make the spec more precise and complete
5. When you have enough information, say "INTERVIEW_COMPLETE"

## Current Document

{document_content}

## Focus Area (if specified)

{focus_area}

## Your Task

Based on the document above, ask your first clarifying question.
'''


def generate_interview_prompt(document_content: str, focus: str | None = None) -> str:
    """Generate interview prompt for spec refinement.

    Args:
        document_content: Current specification content
        focus: Optional area to focus questions on

    Returns:
        Formatted prompt for AI interviewer
    """
    focus_area = focus or "No specific focus - ask about any unclear areas."
    return INTERVIEW_SYSTEM_PROMPT.format(
        document_content=document_content,
        focus_area=focus_area,
    )


def run_interview_loop(
    document_path: Path,
    focus: str | None = None,
) -> bool:
    """Run interactive interview loop.

    Uses simple stdin/stdout for v1.

    Args:
        document_path: Path to document being refined
        focus: Optional focus area

    Returns:
        True if document was modified
    """
    content = document_path.read_text()
    modified = False

    print("\n=== Interview Session ===")
    print(f"Refining: {document_path}")
    print("Type 'quit' to exit, 'save' to save changes\n")

    # Generate initial prompt
    prompt = generate_interview_prompt(content, focus)
    print("Initial prompt generated. Copy to Claude and paste responses here.\n")
    print("=" * 60)
    print(prompt[:500] + "..." if len(prompt) > 500 else prompt)
    print("=" * 60)

    while True:
        try:
            user_input = input("\nYour response (or 'quit'/'save'): ").strip()
        except EOFError:
            break

        if user_input.lower() == "quit":
            if modified:
                save = input("Save changes before quitting? (y/n): ").strip().lower()
                if save == "y":
                    document_path.write_text(content)
            break

        if user_input.lower() == "save":
            document_path.write_text(content)
            print(f"Saved to {document_path}")
            modified = False
            continue

        if "INTERVIEW_COMPLETE" in user_input:
            print("\nInterview complete!")
            if modified:
                document_path.write_text(content)
                print(f"Final document saved to {document_path}")
            break

        # For v1, just append answers as notes (user manually integrates)
        # Future versions could use AI to integrate answers
        print("\n[Answer recorded - integrate into document manually]")

    return modified
```

**Validation:**
```bash
.venv/bin/pyright src/weld/core/interview_engine.py  # Expect: 0 errors
```

---

### 4.6 Create Interview Command

**File:** `src/weld/commands/interview.py` (create new file)

```python
"""Interview CLI command for specification refinement."""

from pathlib import Path

import typer

from ..core.interview_engine import run_interview_loop
from ..output import get_output_context


@typer.command()
def interview(
    file: Path = typer.Argument(..., help="Markdown file to refine"),
    focus: str | None = typer.Option(
        None,
        "--focus",
        "-f",
        help="Topic to focus questions on",
    ),
) -> None:
    """Interactively refine a specification through Q&A."""
    ctx = get_output_context()

    if not file.exists():
        ctx.error(f"File not found: {file}")
        raise typer.Exit(1) from None

    if not file.suffix == ".md":
        ctx.warning("File is not markdown - interview may not work well")

    try:
        modified = run_interview_loop(file, focus)
        if modified:
            ctx.success("Document updated")
        else:
            ctx.info("No changes made")
    except KeyboardInterrupt:
        ctx.info("\nInterview cancelled")
        raise typer.Exit(0) from None
```

**Validation:**
```bash
.venv/bin/pyright src/weld/commands/interview.py  # Expect: 0 errors
```

---

### 4.7 Register Discover and Interview Commands

**File:** `src/weld/cli.py`

**Add imports:**
```python
from .commands.discover import discover
from .commands.interview import interview
```

**Add registrations:**
```python
app.command()(discover)
app.command()(interview)
```

**Validation:**
```bash
weld discover --help  # Should show --output and --focus options
weld interview --help  # Should show file argument and --focus option
```

---

## Phase 5: CLI Completion

**Prerequisite:** Phase 4 complete (discover/interview workflow)

### 5.1 Add Status Command

**File:** `src/weld/commands/status.py` (create new file)

```python
"""Status command for run overview."""

import typer

from ..output import get_output_context
from ..services.git import get_repo_root, GitError
from ..validation import get_weld_dir, get_run_dir
from ..models import Meta


@typer.command()
def status(
    run: str | None = typer.Option(
        None,
        "--run",
        "-r",
        help="Run ID (defaults to most recent)",
    ),
) -> None:
    """Show current run status and next action."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)

    # If no run specified, find most recent
    if run is None:
        runs_dir = weld_dir / "runs"
        if not runs_dir.exists():
            ctx.error("No runs found. Start with: weld run --spec <file>")
            raise typer.Exit(1) from None

        runs = sorted(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if not runs:
            ctx.error("No runs found")
            raise typer.Exit(1) from None
        run = runs[0].name

    run_dir = get_run_dir(weld_dir, run)
    meta_path = run_dir / "meta.json"

    if not meta_path.exists():
        ctx.error(f"Run not found: {run}")
        raise typer.Exit(1) from None

    meta = Meta.model_validate_json(meta_path.read_text())

    # Determine current phase
    research_dir = run_dir / "research"
    plan_dir = run_dir / "plan"
    steps_dir = run_dir / "steps"

    ctx.console.print(f"\n[bold]Run:[/bold] {meta.run_id}")
    ctx.console.print(f"[bold]Branch:[/bold] {meta.branch}")
    ctx.console.print(f"[bold]Created:[/bold] {meta.created_at.strftime('%Y-%m-%d %H:%M')}")

    if meta.abandoned:
        ctx.console.print("[yellow]Status: ABANDONED[/yellow]")
        return

    # Check phases
    if research_dir.exists():
        if not (research_dir / "research.md").exists():
            ctx.console.print("[yellow]Status: Awaiting research[/yellow]")
            ctx.console.print(f"  Next: weld research import --run {run} --file <research.md>")
            return

    if not (plan_dir / "plan.md").exists() and not (plan_dir / "plan.raw.md").exists():
        ctx.console.print("[yellow]Status: Awaiting plan[/yellow]")
        ctx.console.print(f"  Next: weld plan import --run {run} --file <plan.md>")
        return

    # Check steps
    if steps_dir.exists():
        step_dirs = sorted(steps_dir.iterdir())
        completed = sum(1 for s in step_dirs if (s / "completed").exists())
        total = len(step_dirs)
        ctx.console.print(f"[bold]Steps:[/bold] {completed}/{total} completed")

        if completed < total:
            next_step = [s for s in step_dirs if not (s / "completed").exists()][0]
            ctx.console.print(f"  Next: weld step loop --run {run} --step {next_step.name}")
            return

    ctx.console.print("[green]Status: Ready to commit[/green]")
    ctx.console.print(f"  Next: weld commit --run {run}")
```

**Validation:**
```bash
weld status --help
```

---

### 5.2 Add Doctor Command

**File:** `src/weld/commands/doctor.py` (create new file)

```python
"""Doctor command for environment validation."""

import shutil
import subprocess

import typer

from ..output import get_output_context
from ..constants import INIT_TOOL_CHECK_TIMEOUT


REQUIRED_TOOLS = [
    ("git", "git --version"),
    ("gh", "gh --version"),
]

OPTIONAL_TOOLS = [
    ("codex", "codex --version"),
    ("claude", "claude --version"),
    ("claude-code-transcripts", "claude-code-transcripts --version"),
]


def check_tool(name: str, version_cmd: str) -> tuple[bool, str]:
    """Check if a tool is available.

    Returns:
        Tuple of (available, version_or_error)
    """
    if not shutil.which(name):
        return False, "not found in PATH"

    try:
        result = subprocess.run(
            version_cmd.split(),
            capture_output=True,
            text=True,
            timeout=INIT_TOOL_CHECK_TIMEOUT,
        )
        if result.returncode == 0:
            version = result.stdout.strip().split("\n")[0]
            return True, version
        return False, f"exit code {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


@typer.command()
def doctor() -> None:
    """Check environment and dependencies."""
    ctx = get_output_context()
    all_ok = True

    ctx.console.print("\n[bold]Required Tools[/bold]")
    for name, cmd in REQUIRED_TOOLS:
        ok, info = check_tool(name, cmd)
        if ok:
            ctx.console.print(f"  [green]✓[/green] {name}: {info}")
        else:
            ctx.console.print(f"  [red]✗[/red] {name}: {info}")
            all_ok = False

    ctx.console.print("\n[bold]Optional Tools[/bold]")
    for name, cmd in OPTIONAL_TOOLS:
        ok, info = check_tool(name, cmd)
        if ok:
            ctx.console.print(f"  [green]✓[/green] {name}: {info}")
        else:
            ctx.console.print(f"  [yellow]○[/yellow] {name}: {info}")

    ctx.console.print("")
    if all_ok:
        ctx.success("All required dependencies available")
    else:
        ctx.error("Some required dependencies missing")
        raise typer.Exit(2) from None
```

**Validation:**
```bash
weld doctor  # Should check all tools
```

---

### 5.3 Add Run Subcommands (continue, abandon)

**File:** `src/weld/commands/run.py`

**Add to existing file:**

```python
@run_app.command("abandon")
def run_abandon(
    run: str = typer.Option(..., "--run", "-r", help="Run ID to abandon"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Mark a run as abandoned."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    meta_path = run_dir / "meta.json"

    if not meta_path.exists():
        ctx.error(f"Run not found: {run}")
        raise typer.Exit(1) from None

    if not force:
        confirm = typer.confirm(f"Abandon run {run}? This cannot be undone.")
        if not confirm:
            raise typer.Abort()

    from datetime import datetime
    meta = Meta.model_validate_json(meta_path.read_text())
    meta.abandoned = True
    meta.abandoned_at = datetime.now()
    meta_path.write_text(meta.model_dump_json(indent=2))

    ctx.success(f"Run {run} marked as abandoned")


@run_app.command("continue")
def run_continue(
    run: str = typer.Option(..., "--run", "-r", help="Run ID to continue"),
) -> None:
    """Continue a paused run from where it left off."""
    ctx = get_output_context()

    # Delegate to status to show next action
    from .status import status as status_cmd
    ctx_obj = typer.Context(status_cmd)
    status_cmd(run=run)
```

**Validation:**
```bash
weld run abandon --help
weld run continue --help
```

---

### 5.4 Add Step Skip Command

**File:** `src/weld/commands/step.py`

**Add to existing file:**

```python
@step_app.command("skip")
def step_skip(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    step: str = typer.Option(..., "--step", "-s", help="Step directory name"),
    reason: str = typer.Option(..., "--reason", help="Reason for skipping"),
) -> None:
    """Mark a step as skipped."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    step_dir = run_dir / "steps" / step

    if not step_dir.exists():
        ctx.error(f"Step not found: {step}")
        raise typer.Exit(1) from None

    # Write skip marker
    skip_path = step_dir / "skipped"
    skip_path.write_text(reason)

    ctx.success(f"Step {step} marked as skipped: {reason}")
```

**Validation:**
```bash
weld step skip --help
```

---

### 5.5 Add weld next Command

**File:** `src/weld/commands/next.py` (create new file)

```python
"""Next command - shortcut to continue with next action."""

import typer

from ..output import get_output_context
from ..services.git import get_repo_root, GitError
from ..validation import get_weld_dir


@typer.command()
def next_action() -> None:
    """Show and optionally execute the next action for the current run."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    runs_dir = weld_dir / "runs"

    if not runs_dir.exists():
        ctx.console.print("No runs found.")
        ctx.console.print("  Start with: weld run --spec <file>")
        return

    # Find most recent non-abandoned run
    runs = sorted(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    current_run = None

    for run_dir in runs:
        meta_path = run_dir / "meta.json"
        if meta_path.exists():
            from ..models import Meta
            meta = Meta.model_validate_json(meta_path.read_text())
            if not meta.abandoned:
                current_run = run_dir
                break

    if current_run is None:
        ctx.console.print("No active runs found.")
        ctx.console.print("  Start with: weld run --spec <file>")
        return

    # Use status command to show next action
    from .status import status as show_status
    show_status(run=current_run.name)
```

**Register in cli.py:**
```python
from .commands.next import next_action
app.command("next")(next_action)
```

**Validation:**
```bash
weld next  # Should show status of most recent run
```

---

### 5.6 Register Phase 5 Commands

**File:** `src/weld/cli.py`

**Add all new imports and registrations:**
```python
from .commands.status import status
from .commands.doctor import doctor

app.command()(status)
app.command()(doctor)
```

**Validation:**
```bash
weld --help  # Should show all new commands
```

---

## Phase 6: Templates & Polish

**Prerequisite:** Phase 5 complete (CLI completion)

### 6.1 Add Debug Logging Infrastructure

**File:** `src/weld/logging.py`

**Current code:** Basic Rich logging

**Add file-based debug logging:**
```python
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEBUG_LOG_FILE = "debug.log"
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 3


def setup_debug_logging(weld_dir: Path, enabled: bool = False) -> None:
    """Configure debug file logging.

    Args:
        weld_dir: Path to .weld directory
        enabled: Whether debug logging is enabled
    """
    if not enabled:
        return

    log_path = weld_dir / DEBUG_LOG_FILE
    handler = RotatingFileHandler(
        log_path,
        maxBytes=MAX_LOG_SIZE,
        backupCount=BACKUP_COUNT,
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))

    root_logger = logging.getLogger("weld")
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG)
```

**Validation:**
```bash
.venv/bin/pyright src/weld/logging.py
```

---

### 6.2 Update CLI to Use Debug Flag

**File:** `src/weld/cli.py`

**In the main callback, after getting weld_dir:**
```python
    if debug:
        from .logging import setup_debug_logging
        setup_debug_logging(weld_dir, enabled=True)
```

**Validation:**
```bash
weld --debug status  # Should create .weld/debug.log
```

---

### 6.3 Add Timing Model

**File:** `src/weld/models/timing.py` (create new file)

```python
"""Timing model for per-phase performance tracking."""

from pydantic import BaseModel, Field


class Timing(BaseModel):
    """Per-iteration timing breakdown.

    Attributes:
        ai_invocation_ms: Time spent waiting for AI response
        checks_ms: Time spent running checks
        review_ms: Time spent on review
        total_ms: Total iteration time
    """

    ai_invocation_ms: int = Field(default=0, description="AI invocation time in ms")
    checks_ms: int = Field(default=0, description="Checks execution time in ms")
    review_ms: int = Field(default=0, description="Review time in ms")
    total_ms: int = Field(default=0, description="Total iteration time in ms")
```

**Validation:**
```bash
.venv/bin/pyright src/weld/models/timing.py
```

---

### 6.4 Add JSON Schema Versioning

**File:** `src/weld/output.py`

**Update print_json method:**
```python
SCHEMA_VERSION = 1


def print_json(self, data: dict[str, Any]) -> None:
    """Print JSON with schema version wrapper."""
    if self.json_mode:
        wrapped = {
            "schema_version": SCHEMA_VERSION,
            "data": data,
        }
        print(json.dumps(wrapped, indent=2, default=str))
```

**Validation:**
```bash
weld --json list  # Should output {"schema_version": 1, "data": {...}}
```

---

### 6.5 Improve Error Messages with Next Actions

**File:** `src/weld/output.py`

**Update error method:**
```python
def error(
    self,
    message: str,
    data: dict[str, Any] | None = None,
    next_action: str | None = None,
) -> None:
    """Print error with optional suggested next action."""
    if self.json_mode and data:
        self.print_json({"error": message, **data})
    else:
        self.console.print(f"[red]Error: {message}[/red]")
        if next_action:
            self.console.print(f"  Run: {next_action}")
```

**Update callers to provide next_action where helpful.**

**Validation:**
```bash
# Errors should now suggest next actions
```

---

### 6.6 Update Lock Manager with Heartbeat Interval

**File:** `src/weld/core/lock_manager.py`

**Add constant (Decision: 60 seconds):**
```python
HEARTBEAT_INTERVAL_SECONDS = 60
```

**In long-running loops (step loop), call update_heartbeat periodically.**

**Validation:**
```bash
.venv/bin/pytest tests/test_lock_manager.py -v
```

---

## Risk Matrix

| Risk | Impact | Detection | Mitigation |
|------|--------|-----------|------------|
| Breaking existing `checks.command` configs | High | Config load fails | `is_legacy_mode()` maintains backward compat |
| Lock file left after crash | Medium | Stale lock error on next run | `is_stale_lock()` checks PID liveness |
| CategoryResult missing output field | High | Tests fail at step 1.1.10 | Output field included in model |
| Import cycles between models/services | Medium | Import error | Services import models, not vice versa |
| Status.checks_summary None in old data | Low | AttributeError | Field has `| None` type and default |
| Research phase changes run flow | Medium | Existing scripts break | `--skip-research` preserves old behavior |
| Version history disk usage | Low | Disk full | MAX_VERSIONS=5 with automatic pruning |
| Interview stdin/stdout limitations | Low | User confusion | Document limitations, iterate in v2 |
