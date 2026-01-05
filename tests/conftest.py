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
