# Enterprise-Grade Quality Implementation Plan

> **Generated**: 2026-01-04
> **Reference**: BEST_PRACTICES.md
> **Current State**: Core functionality complete, basic tests passing

---

## Executive Summary

This plan transforms the `weld-cli` repository from a functional prototype to enterprise-grade quality. The assessment identified **8 major gap categories** requiring remediation across code architecture, quality gates, security, testing, and DevOps.

### Current State Assessment

| Metric | Status | Notes |
|--------|--------|-------|
| Source Files | 19 | Flat structure in `src/weld/` |
| Test Files | 4 | 16 tests passing |
| Ruff Lint | ✅ Pass | Default rules only |
| Mypy | ✅ Pass | `--ignore-missing-imports` |
| Pyright | ❌ Missing | Not configured |
| Pre-commit | ❌ Missing | No hooks |
| CI/CD | ❌ Missing | No GitHub Actions |
| Security Scanning | ❌ Missing | No pip-audit/detect-secrets |
| Coverage | ❌ Missing | No coverage tracking |
| CLI Tests | ❌ Missing | No CliRunner tests |

---

## Phase 1: Project Configuration & Quality Gates **COMPLETE**

**Goal**: Establish strict quality gates that match enterprise standards.

### Step 1.1: Fix pyproject.toml Configuration

**Current Issues**:
- `requires-python = ">=3.14"` — too restrictive, should be `>=3.11`
- Missing ruff lint rules (`E`, `F`, `I`, `UP`, `B`, `SIM`, `C4`, `RUF`)
- Missing ruff format configuration
- Missing pyright configuration
- Missing `src` path directive for ruff

**File**: `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "weld"
version = "0.1.0"
description = "Human-in-the-loop coding harness: plan, review, iterate, commit with transcript provenance"
requires-python = ">=3.11"
dependencies = [
  "typer>=0.12",
  "pydantic>=2.6",
  "rich>=13.7",
  "tomli-w>=1.0",
]

[project.scripts]
weld = "weld.cli:app"

[dependency-groups]
dev = [
  "pytest>=8",
  "pytest-cov>=5.0",
  "ruff>=0.5",
  "pyright>=1.1",
  "pre-commit>=3.7",
  "pip-audit>=2.7",
  "detect-secrets>=1.5",
]

[tool.hatch.build.targets.wheel]
packages = ["src/weld"]

[tool.ruff]
target-version = "py311"
line-length = 100
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "C4", "RUF"]
ignore = []

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.pyright]
typeCheckingMode = "standard"
pythonVersion = "3.11"
include = ["src"]
exclude = ["**/__pycache__", ".venv"]
reportMissingImports = true
reportMissingTypeStubs = false

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"
markers = [
    "unit: Unit tests for pure logic",
    "cli: CLI integration tests",
    "slow: Tests that take significant time",
]

[tool.coverage.run]
source = ["src/weld"]
branch = true
omit = ["*/tests/*", "*/__pycache__/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]
fail_under = 80
```

**Validation**:
```bash
uv sync
uv run ruff check .
uv run pyright
```

---

### Step 1.2: Create Pre-commit Configuration

**File**: `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/RobertCraigie/pyright-python
    rev: v1.1.370
    hooks:
      - id: pyright

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
        exclude: 'uv.lock'

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict
```

**Setup**:
```bash
uv run pre-commit install
uv run detect-secrets scan > .secrets.baseline
uv run pre-commit run -a
```

---

### Step 1.3: Create GitHub Actions CI Workflow

**File**: `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          version: "latest"
      - name: Install dependencies
        run: uv sync --frozen
      - name: Check formatting
        run: uv run ruff format --check .
      - name: Lint
        run: uv run ruff check .
      - name: Type check
        run: uv run pyright

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          version: "latest"
      - name: Set Python version
        run: uv python pin ${{ matrix.python-version }}
      - name: Install dependencies
        run: uv sync --frozen
      - name: Run tests with coverage
        run: uv run pytest --cov=src/weld --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          version: "latest"
      - name: Install dependencies
        run: uv sync --frozen
      - name: Audit dependencies
        run: uv run pip-audit
      - name: Secret scanning
        run: uv run detect-secrets scan --baseline .secrets.baseline
```

---

## Phase 2: CLI Best Practices ✅ COMPLETE

**Goal**: Implement enterprise CLI patterns: versioning, verbosity, structured output.

### Step 2.1: Add --version Command

**File**: `src/weld/cli.py` (modification)

```python
# Add to imports
from weld import __version__

# Add version callback
def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"weld {__version__}")
        raise typer.Exit()

# Modify app definition
app = typer.Typer(
    name="weld",
    help="Human-in-the-loop coding harness with transcript provenance",
    no_args_is_help=True,
)

@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """Weld CLI - Human-in-the-loop coding harness."""
    pass
```

---

### Step 2.2: Add Verbosity and Logging Control

**File**: `src/weld/logging.py` (new)

```python
"""Logging configuration for weld CLI."""

import logging
import sys
from enum import IntEnum
from typing import TextIO

from rich.console import Console
from rich.logging import RichHandler


class LogLevel(IntEnum):
    """Log level enumeration."""

    QUIET = logging.WARNING
    NORMAL = logging.INFO
    VERBOSE = logging.DEBUG


def configure_logging(
    verbosity: int = 0,
    quiet: bool = False,
    no_color: bool = False,
    stream: TextIO = sys.stderr,
) -> Console:
    """Configure logging based on CLI options.

    Args:
        verbosity: Number of -v flags (0=normal, 1=verbose, 2+=debug)
        quiet: Suppress non-error output
        no_color: Disable colored output
        stream: Output stream for logs

    Returns:
        Configured Rich console for output
    """
    if quiet:
        level = LogLevel.QUIET
    elif verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = LogLevel.VERBOSE
    else:
        level = LogLevel.NORMAL

    console = Console(
        stderr=True,
        force_terminal=not no_color if not no_color else False,
        no_color=no_color,
    )

    handler = RichHandler(
        console=console,
        show_time=verbosity >= 2,
        show_path=verbosity >= 2,
    )

    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[handler],
    )

    return console
```

---

### Step 2.3: Add JSON Output Option

**File**: `src/weld/output.py` (new)

```python
"""Output formatting for weld CLI."""

import json
from dataclasses import dataclass
from typing import Any

from rich.console import Console


@dataclass
class OutputContext:
    """Context for output formatting."""

    console: Console
    json_mode: bool = False

    def print(self, message: str, style: str | None = None) -> None:
        """Print message respecting output mode."""
        if not self.json_mode:
            self.console.print(message, style=style)

    def print_json(self, data: dict[str, Any]) -> None:
        """Print JSON data."""
        if self.json_mode:
            print(json.dumps(data, indent=2, default=str))

    def result(self, data: dict[str, Any], message: str = "") -> None:
        """Print result in appropriate format."""
        if self.json_mode:
            self.print_json(data)
        elif message:
            self.console.print(message)

    def error(self, message: str, data: dict[str, Any] | None = None) -> None:
        """Print error in appropriate format."""
        if self.json_mode and data:
            self.print_json({"error": message, **data})
        else:
            self.console.print(f"[red]Error: {message}[/red]")
```

---

### Step 2.4: Update CLI with Global Options

**File**: `src/weld/cli.py` (modification to callback)

```python
from weld.logging import configure_logging
from weld.output import OutputContext

# Global context
_ctx: OutputContext | None = None

def get_output_context() -> OutputContext:
    """Get the current output context."""
    if _ctx is None:
        return OutputContext(Console())
    return _ctx

@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V",
        callback=version_callback, is_eager=True,
        help="Show version and exit",
    ),
    verbose: int = typer.Option(
        0, "--verbose", "-v", count=True,
        help="Increase verbosity (-v, -vv)",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q",
        help="Suppress non-error output",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output in JSON format for automation",
    ),
    no_color: bool = typer.Option(
        False, "--no-color",
        help="Disable colored output",
    ),
) -> None:
    """Weld CLI - Human-in-the-loop coding harness."""
    global _ctx
    console = configure_logging(
        verbosity=verbose,
        quiet=quiet,
        no_color=no_color,
    )
    _ctx = OutputContext(console=console, json_mode=json_output)
```

---

## Phase 3: Security Hardening ✅ COMPLETE

**Goal**: Eliminate security vulnerabilities and establish secure coding patterns.

### Step 3.1: Remove shell=True from subprocess calls

**Issue**: `checks.py` uses `shell=True` which allows command injection.

**File**: `src/weld/checks.py` (rewrite)

```python
"""Checks runner for weld."""

import shlex
import subprocess
from pathlib import Path

# Timeout for checks (5 minutes)
CHECKS_TIMEOUT_SECONDS = 300


class ChecksError(Exception):
    """Error running checks."""
    pass


def run_checks(command: str, cwd: Path, timeout: int | None = None) -> tuple[str, int]:
    """Run checks command and return (output, exit_code).

    Args:
        command: Shell command to run (will be parsed safely)
        cwd: Working directory
        timeout: Optional timeout in seconds (default: 300)

    Returns:
        Tuple of (formatted output with stdout/stderr, exit code)

    Raises:
        ChecksError: If command times out or fails to execute
    """
    timeout = timeout or CHECKS_TIMEOUT_SECONDS

    try:
        # Parse command safely - this handles quoting properly
        args = shlex.split(command)
    except ValueError as e:
        raise ChecksError(f"Invalid command syntax: {e}")

    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ChecksError(f"Checks timed out after {timeout} seconds")
    except FileNotFoundError:
        raise ChecksError(f"Command not found: {args[0]}")

    output = f"exit_code: {result.returncode}\n\n"
    output += "=== stdout ===\n"
    output += result.stdout
    output += "\n=== stderr ===\n"
    output += result.stderr
    return output, result.returncode


def write_checks(path: Path, output: str) -> None:
    """Write checks output to file.

    Args:
        path: File path to write to
        output: Checks output content
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output)
```

**Note**: This change requires updating `config.toml` documentation to use simple commands or scripts that don't require shell features. For complex commands, users should wrap them in a shell script.

---

### Step 3.2: Add Consistent Timeouts to All Subprocess Calls

**File**: `src/weld/constants.py` (new)

```python
"""Constants for weld CLI."""

# Subprocess timeouts (seconds)
GIT_TIMEOUT = 30
CODEX_TIMEOUT = 600  # 10 minutes for AI operations
TRANSCRIPT_TIMEOUT = 60
INIT_TOOL_CHECK_TIMEOUT = 10
```

Update all subprocess.run() calls to use these constants.

---

### Step 3.3: Input Validation for File Paths

**File**: `src/weld/validation.py` (new)

```python
"""Input validation utilities."""

from pathlib import Path


class ValidationError(Exception):
    """Validation failed."""
    pass


def validate_path_within_repo(path: Path, repo_root: Path) -> Path:
    """Ensure path is within repository bounds.

    Args:
        path: Path to validate
        repo_root: Repository root directory

    Returns:
        Resolved absolute path

    Raises:
        ValidationError: If path escapes repository
    """
    resolved = path.resolve()
    repo_resolved = repo_root.resolve()

    try:
        resolved.relative_to(repo_resolved)
    except ValueError:
        raise ValidationError(
            f"Path {path} is outside repository {repo_root}"
        )

    return resolved


def validate_run_id(run_id: str) -> str:
    """Validate run ID format.

    Args:
        run_id: Run ID to validate

    Returns:
        Validated run ID

    Raises:
        ValidationError: If run ID is invalid
    """
    import re

    # Format: YYYYMMDD-HHMMSS-slug
    pattern = r"^\d{8}-\d{6}-[a-z0-9-]+$"
    if not re.match(pattern, run_id):
        raise ValidationError(
            f"Invalid run ID format: {run_id}. "
            "Expected: YYYYMMDD-HHMMSS-slug"
        )

    return run_id
```

---

## Phase 4: Architecture Refactoring

**Goal**: Refactor to enterprise CLI architecture (core/services/commands separation).

### Step 4.1: Create Directory Structure

```
src/weld/
  __init__.py
  __main__.py           # NEW: python -m weld support
  cli.py                # Thin CLI layer (argument parsing only)

  core/                 # NEW: Pure business logic
    __init__.py
    plan_parser.py      # Plan parsing logic (from plan.py)
    step_processor.py   # Step processing logic
    review_engine.py    # Review logic

  services/             # NEW: External integrations
    __init__.py
    git.py              # Git operations
    codex.py            # Codex API calls
    filesystem.py       # File I/O operations
    transcripts.py      # Transcript generation

  models/               # EXISTING: Data models
    __init__.py
    meta.py
    step.py
    issues.py
    status.py

  commands/             # NEW: Command implementations
    __init__.py
    init.py
    run.py
    plan.py
    step.py
    commit.py
```

### Step 4.2: Create __main__.py

**File**: `src/weld/__main__.py`

```python
"""Entry point for python -m weld."""

from weld.cli import app

if __name__ == "__main__":
    app()
```

---

## Phase 5: Testing Enhancement

**Goal**: Achieve 80%+ coverage with CLI, unit, and integration tests.

### Step 5.1: Create CLI Test Fixtures

**File**: `tests/conftest.py`

```python
"""Shared test fixtures."""

import os
from pathlib import Path
from typing import Generator

import pytest
from typer.testing import CliRunner

from weld.cli import app


@pytest.fixture
def runner() -> CliRunner:
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary git repository."""
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path, check=True, capture_output=True
    )

    # Create initial commit
    (tmp_path / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path, check=True, capture_output=True
    )

    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(original_cwd)


@pytest.fixture
def initialized_weld(temp_git_repo: Path, runner: CliRunner) -> Path:
    """Create initialized weld directory."""
    weld_dir = temp_git_repo / ".weld"
    weld_dir.mkdir()
    (weld_dir / "runs").mkdir()

    # Create minimal config
    config = '''
[project]
name = "test-project"

[checks]
command = "echo ok"

[codex]
exec = "echo"
sandbox = "read-only"
'''
    (weld_dir / "config.toml").write_text(config)

    return temp_git_repo
```

---

### Step 5.2: Create CLI Tests

**File**: `tests/test_cli.py`

```python
"""CLI integration tests."""

import pytest
from typer.testing import CliRunner

from weld.cli import app


class TestVersionCommand:
    """Tests for --version flag."""

    def test_version_shows_version(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "weld" in result.stdout
        assert "0.1.0" in result.stdout


class TestHelpCommand:
    """Tests for --help flag."""

    def test_help_shows_commands(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "init" in result.stdout
        assert "run" in result.stdout
        assert "plan" in result.stdout
        assert "step" in result.stdout
        assert "commit" in result.stdout


class TestInitCommand:
    """Tests for weld init."""

    def test_init_not_git_repo(self, runner: CliRunner, tmp_path) -> None:
        import os
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(app, ["init"])
            assert result.exit_code == 3
            assert "Not a git repository" in result.stdout
        finally:
            os.chdir(original)

    def test_init_success(self, runner: CliRunner, temp_git_repo) -> None:
        # Mock tool checks to pass
        result = runner.invoke(app, ["init"])
        # May exit 2 if tools missing, but should not crash
        assert result.exit_code in [0, 2]


class TestListCommand:
    """Tests for weld list."""

    def test_list_no_runs(self, runner: CliRunner, initialized_weld) -> None:
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No runs found" in result.stdout


class TestRunCommand:
    """Tests for weld run."""

    def test_run_spec_not_found(self, runner: CliRunner, initialized_weld) -> None:
        result = runner.invoke(app, ["run", "--spec", "nonexistent.md"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()


class TestErrorHandling:
    """Tests for error handling."""

    def test_invalid_subcommand(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["invalid"])
        assert result.exit_code != 0
```

---

### Step 5.3: Create Unit Tests for Core Logic

**File**: `tests/test_validation.py`

```python
"""Tests for validation utilities."""

import pytest
from pathlib import Path

from weld.validation import ValidationError, validate_path_within_repo, validate_run_id


class TestPathValidation:
    """Tests for path validation."""

    def test_valid_path_within_repo(self, tmp_path: Path) -> None:
        sub_path = tmp_path / "subdir" / "file.txt"
        result = validate_path_within_repo(sub_path, tmp_path)
        assert result.is_relative_to(tmp_path)

    def test_path_escape_rejected(self, tmp_path: Path) -> None:
        escape_path = tmp_path / ".." / "outside"
        with pytest.raises(ValidationError, match="outside repository"):
            validate_path_within_repo(escape_path, tmp_path)


class TestRunIdValidation:
    """Tests for run ID validation."""

    def test_valid_run_id(self) -> None:
        result = validate_run_id("20260104-120000-my-feature")
        assert result == "20260104-120000-my-feature"

    def test_invalid_run_id_format(self) -> None:
        with pytest.raises(ValidationError, match="Invalid run ID"):
            validate_run_id("invalid-format")

    def test_invalid_run_id_uppercase(self) -> None:
        with pytest.raises(ValidationError, match="Invalid run ID"):
            validate_run_id("20260104-120000-MyFeature")
```

---

### Step 5.4: Create Integration Test Script

**File**: `tests/test_integration.py`

```python
"""Integration tests for full workflows."""

import pytest
from pathlib import Path
from typer.testing import CliRunner

from weld.cli import app


@pytest.mark.slow
class TestFullWorkflow:
    """Test complete weld workflow."""

    def test_init_to_run_workflow(
        self,
        runner: CliRunner,
        temp_git_repo: Path,
    ) -> None:
        # Create spec file
        spec_path = temp_git_repo / "spec.md"
        spec_path.write_text("""# Test Spec

## Requirements
- Create hello.py with greet() function
""")

        # Initialize weld (may fail on missing tools)
        weld_dir = temp_git_repo / ".weld"
        weld_dir.mkdir()
        (weld_dir / "runs").mkdir()
        (weld_dir / "config.toml").write_text('''
[project]
name = "test"
[checks]
command = "echo ok"
[codex]
exec = "echo"
''')

        # Start a run
        result = runner.invoke(app, ["run", "--spec", str(spec_path)])
        assert result.exit_code == 0
        assert "Run created" in result.stdout

        # Verify run directory created
        runs = list((weld_dir / "runs").iterdir())
        assert len(runs) == 1

        run_id = runs[0].name

        # List runs
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert run_id in result.stdout
```

---

## Phase 6: Documentation

**Goal**: Ensure all public APIs are documented with docstrings.

### Step 6.1: Add Module Docstrings

Every module should have a docstring explaining its purpose:

```python
"""Module description.

This module provides...

Example:
    >>> from weld.module import function
    >>> function()
"""
```

### Step 6.2: Add Function Docstrings (Google Style)

```python
def function(arg1: str, arg2: int) -> bool:
    """Brief description.

    Longer description if needed.

    Args:
        arg1: Description of arg1
        arg2: Description of arg2

    Returns:
        Description of return value

    Raises:
        ValueError: When arg1 is empty

    Example:
        >>> function("test", 42)
        True
    """
```

---

## Phase 7: Release Readiness

**Goal**: Prepare for packaging and distribution.

### Step 7.1: Add CHANGELOG.md

**File**: `CHANGELOG.md`

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of weld CLI
- Human-in-the-loop coding workflow
- Plan generation and review
- Step implementation with review loop
- Transcript provenance tracking
- Git commit trailers

### Security
- Input validation for file paths
- Removed shell=True from subprocess calls
- Timeout enforcement on all subprocess calls
```

### Step 7.2: Add py.typed Marker

**File**: `src/weld/py.typed`

```
# Marker file for PEP 561
```

---

## Implementation Priority Matrix

| Phase | Priority | Effort | Impact | Dependencies |
|-------|----------|--------|--------|--------------|
| 1. Quality Gates | P0 | Medium | High | None |
| 2. CLI Best Practices | P1 | Medium | High | None |
| 3. Security Hardening | P0 | Low | Critical | None |
| 4. Architecture Refactor | P2 | High | Medium | Phase 1-3 |
| 5. Testing Enhancement | P1 | Medium | High | Phase 1 |
| 6. Documentation | P2 | Low | Medium | Phase 4 |
| 7. Release Readiness | P3 | Low | Medium | All |

---

## Quick Wins (Can Implement Today)

1. **Fix pyproject.toml** (Step 1.1) — 15 minutes
2. **Add pre-commit config** (Step 1.2) — 10 minutes
3. **Add __main__.py** (Step 4.2) — 2 minutes
4. **Add py.typed** (Step 7.2) — 1 minute
5. **Create constants.py** (Step 3.2) — 5 minutes

---

## Validation Checklist

After implementation, verify:

```bash
# Quality gates pass
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -v --cov=src/weld --cov-report=term-missing
uv run pip-audit

# Pre-commit works
uv run pre-commit run -a

# CLI works
uv run weld --version
uv run weld --help
python -m weld --version

# Coverage meets threshold
# Should show ≥80% coverage
```

---

## Exit Criteria

The repository achieves enterprise-grade quality when:

- [ ] All ruff lint rules pass (E, F, I, UP, B, SIM, C4, RUF)
- [ ] Pyright type checking passes with "standard" mode
- [ ] Test coverage ≥ 80%
- [ ] All CLI commands have corresponding tests
- [ ] Pre-commit hooks installed and passing
- [ ] GitHub Actions CI passing on push/PR
- [ ] pip-audit shows no vulnerabilities
- [ ] detect-secrets baseline established
- [x] All subprocess calls have timeouts
- [x] No shell=True in subprocess calls
- [ ] All public functions have docstrings
- [x] --version, --verbose, --json, --no-color flags work
- [ ] python -m weld works
