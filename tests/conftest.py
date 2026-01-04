"""Shared test fixtures for weld tests."""

import os
import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary git repository.

    Initializes a git repo with user config and an initial commit.
    Changes cwd to the repo directory for the duration of the test.
    """
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    (tmp_path / "README.md").write_text("# Test\n")
    subprocess.run(
        ["git", "add", "."],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(original_cwd)


@pytest.fixture
def initialized_weld(temp_git_repo: Path) -> Path:
    """Create initialized weld directory with minimal config.

    Returns the repo root path with .weld directory already set up.
    """
    weld_dir = temp_git_repo / ".weld"
    weld_dir.mkdir()
    (weld_dir / "runs").mkdir()

    # Create minimal config
    config = """[project]
name = "test-project"

[checks]
command = "echo ok"

[codex]
exec = "echo"
sandbox = "read-only"

[claude]
exec = "echo"
"""
    (weld_dir / "config.toml").write_text(config)

    return temp_git_repo


@pytest.fixture
def sample_plan() -> str:
    """Return a sample plan in strict format."""
    return """## Step 1: Create hello module

### Goal
Create a hello world module.

### Changes
- Create src/hello.py with greet() function

### Acceptance criteria
- [ ] Function returns "Hello, World!"
- [ ] Module can be imported

### Tests
- pytest tests/test_hello.py

## Step 2: Add CLI command

### Goal
Add a CLI command to run greet.

### Changes
- Update cli.py to add hello command

### Acceptance criteria
- [ ] weld hello prints greeting

### Tests
- weld hello
"""


@pytest.fixture
def run_with_plan(initialized_weld: Path, sample_plan: str) -> tuple[Path, str]:
    """Create an initialized weld with a run and plan.

    Returns tuple of (repo_root, run_id).
    """
    weld_dir = initialized_weld / ".weld"
    run_id = "20260104-120000-test-run"

    run_dir = weld_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "plan").mkdir()
    (run_dir / "steps").mkdir()

    # Create meta.json
    import json

    meta = {
        "run_id": run_id,
        "repo_root": str(initialized_weld),
        "branch": "master",
        "head_sha": "abc123",
        "config_hash": "hash123",
        "created_at": "2026-01-04T12:00:00",
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    # Create plan files
    (run_dir / "plan" / "plan.raw.md").write_text(sample_plan)
    (run_dir / "plan" / "plan.final.md").write_text(sample_plan)

    return initialized_weld, run_id
