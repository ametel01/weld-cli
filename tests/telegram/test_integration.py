"""End-to-end integration tests for Telegram bot CLI.

Tests the full flow: init → projects add → use → doctor → status
with mocked aiogram Bot.
"""

from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from weld.cli import app
from weld.telegram.config import (
    TelegramAuth,
    TelegramConfig,
    TelegramProject,
    load_config,
    save_config,
)


def mock_asyncio_run(return_value: Any) -> Any:
    """Create a mock for asyncio.run that properly closes coroutines.

    This prevents 'coroutine was never awaited' warnings by closing
    the coroutine before returning the mocked value.
    """

    def _mock_run(coro: Coroutine[Any, Any, Any]) -> Any:
        coro.close()
        return return_value

    return _mock_run


@pytest.fixture
def integration_runner() -> CliRunner:
    """Create CLI test runner with isolated environment for integration tests."""
    return CliRunner(
        env={
            "NO_COLOR": "1",
            "TERM": "dumb",
            "COLUMNS": "200",
        },
    )


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory."""
    config_path = tmp_path / ".config" / "weld"
    config_path.mkdir(parents=True)
    return config_path


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    project_path = tmp_path / "myproject"
    project_path.mkdir()
    return project_path


def get_output(result: object) -> str:
    """Get combined stdout and output from result for assertion checking."""
    output = getattr(result, "output", None)
    if output:
        return output
    return getattr(result, "stdout", "") or ""


def create_mock_bot() -> MagicMock:
    """Create a mock aiogram Bot with common methods stubbed."""
    mock_bot = MagicMock()
    mock_bot.get_me = AsyncMock()
    mock_bot.session = MagicMock()
    mock_bot.session.close = AsyncMock()
    return mock_bot


@pytest.mark.cli
class TestEndToEndFlow:
    """End-to-end integration tests for the full Telegram CLI workflow."""

    def test_full_workflow_init_to_status(
        self,
        integration_runner: CliRunner,
        config_dir: Path,
        project_dir: Path,
    ) -> None:
        """Test full workflow: init → projects add → doctor (all checks pass)."""
        config_path = config_dir / "telegram.toml"

        # Step 1: Initialize with valid token
        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@testbot"))),
        ):
            result = integration_runner.invoke(app, ["telegram", "init", "-t", "123456:ABC"])
            assert result.exit_code == 0, f"init failed: {get_output(result)}"
            output = get_output(result)
            assert "Token valid" in output
            assert "@testbot" in output
            assert config_path.exists()

        # Verify config was created correctly
        loaded_config = load_config(config_path)
        assert loaded_config.bot_token == "123456:ABC"

        # Step 2: Add a project
        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = integration_runner.invoke(
                app,
                [
                    "telegram",
                    "projects",
                    "add",
                    "testproject",
                    str(project_dir),
                    "-d",
                    "Test project for integration",
                ],
            )
            assert result.exit_code == 0, f"projects add failed: {get_output(result)}"
            output = get_output(result)
            assert "Added project" in output
            assert "testproject" in output

        # Verify project was added
        loaded_config = load_config(config_path)
        assert len(loaded_config.projects) == 1
        assert loaded_config.projects[0].name == "testproject"
        assert loaded_config.projects[0].path == project_dir

        # Step 3: List projects
        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = integration_runner.invoke(app, ["telegram", "projects", "list"])
            assert result.exit_code == 0, f"projects list failed: {get_output(result)}"
            output = get_output(result)
            assert "testproject" in output
            assert str(project_dir) in output
            assert "Test project for integration" in output

        # Step 4: Run doctor (should pass with valid config + project)
        # Need to add an allowed user to pass all checks
        config = load_config(config_path)
        config.auth = TelegramAuth(allowed_user_ids=[12345])
        save_config(config, config_path)

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@testbot"))),
        ):
            result = integration_runner.invoke(app, ["telegram", "doctor"])
            assert result.exit_code == 0, f"doctor failed: {get_output(result)}"
            output = get_output(result)
            assert "All checks passed" in output

        # Step 5: Check whoami
        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@testbot"))),
        ):
            result = integration_runner.invoke(app, ["telegram", "whoami"])
            assert result.exit_code == 0, f"whoami failed: {get_output(result)}"
            output = get_output(result)
            assert "Authenticated" in output
            assert "@testbot" in output
            assert "1 IDs" in output  # We added one allowed user
            assert "1 registered" in output  # We added one project

    def test_workflow_without_allowed_users(
        self,
        integration_runner: CliRunner,
        config_dir: Path,
        project_dir: Path,
    ) -> None:
        """Test workflow warns when no allowed users configured."""
        config_path = config_dir / "telegram.toml"

        # Initialize
        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@testbot"))),
        ):
            result = integration_runner.invoke(app, ["telegram", "init", "-t", "123:ABC"])
            assert result.exit_code == 0

        # Add project
        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = integration_runner.invoke(
                app, ["telegram", "projects", "add", "proj", str(project_dir)]
            )
            assert result.exit_code == 0

        # Doctor should warn about no allowed users but still exit 0
        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@testbot"))),
        ):
            result = integration_runner.invoke(app, ["telegram", "doctor"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "No allowed users" in output

    def test_workflow_project_operations(
        self,
        integration_runner: CliRunner,
        config_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test add, list, and remove project operations in sequence."""
        config_path = config_dir / "telegram.toml"

        # Create initial config
        config = TelegramConfig(bot_token="test:token")
        save_config(config, config_path)

        # Create multiple project directories
        proj1 = tmp_path / "project1"
        proj1.mkdir()
        proj2 = tmp_path / "project2"
        proj2.mkdir()

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            # Add first project
            result = integration_runner.invoke(
                app, ["telegram", "projects", "add", "proj1", str(proj1), "-d", "First project"]
            )
            assert result.exit_code == 0
            assert "Added project" in get_output(result)

            # Add second project
            result = integration_runner.invoke(
                app, ["telegram", "projects", "add", "proj2", str(proj2)]
            )
            assert result.exit_code == 0

            # List should show both
            result = integration_runner.invoke(app, ["telegram", "projects", "list"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "proj1" in output
            assert "proj2" in output
            assert "First project" in output

            # Remove first project
            result = integration_runner.invoke(app, ["telegram", "projects", "remove", "proj1"])
            assert result.exit_code == 0
            assert "Removed project" in get_output(result)

            # List should show only second
            result = integration_runner.invoke(app, ["telegram", "projects", "list"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "proj1" not in output
            assert "proj2" in output

            # Remove second project
            result = integration_runner.invoke(app, ["telegram", "projects", "remove", "proj2"])
            assert result.exit_code == 0

            # List should show empty
            result = integration_runner.invoke(app, ["telegram", "projects", "list"])
            assert result.exit_code == 0
            assert "No projects registered" in get_output(result)

    def test_workflow_reinit_with_force(
        self,
        integration_runner: CliRunner,
        config_dir: Path,
    ) -> None:
        """Test reinitializing config with --force preserves projects."""
        config_path = config_dir / "telegram.toml"
        project_dir = config_dir / "myproject"
        project_dir.mkdir()

        # Create initial config with a project
        config = TelegramConfig(
            bot_token="old:token",
            projects=[TelegramProject(name="myproject", path=project_dir)],
            auth=TelegramAuth(allowed_user_ids=[123]),
        )
        save_config(config, config_path)

        # Reinitialize without --force should fail
        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
        ):
            result = integration_runner.invoke(app, ["telegram", "init", "-t", "new:token"])
            assert result.exit_code == 1
            assert "already exists" in get_output(result)

        # Reinitialize with --force
        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@newbot"))),
        ):
            result = integration_runner.invoke(
                app, ["telegram", "init", "-t", "new:token", "--force"]
            )
            assert result.exit_code == 0
            output = get_output(result)
            assert "@newbot" in output

        # Verify token was updated
        loaded = load_config(config_path)
        assert loaded.bot_token == "new:token"


@pytest.mark.cli
class TestErrorRecovery:
    """Tests for error handling and recovery in CLI workflow."""

    def test_init_recovers_from_invalid_config(
        self,
        integration_runner: CliRunner,
        config_dir: Path,
    ) -> None:
        """Test init can recover from corrupted config file."""
        config_path = config_dir / "telegram.toml"

        # Create invalid config file
        config_path.write_text("this is [ invalid toml")

        # Init should be able to overwrite the invalid config
        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@testbot"))),
        ):
            # Without --force, init should allow overwriting invalid config
            result = integration_runner.invoke(app, ["telegram", "init", "-t", "123:ABC"])
            assert result.exit_code == 0
            assert "Token valid" in get_output(result)

        # Verify config is now valid
        loaded = load_config(config_path)
        assert loaded.bot_token == "123:ABC"

    def test_doctor_reports_all_issues(
        self,
        integration_runner: CliRunner,
        config_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test doctor reports multiple issues correctly."""
        config_path = config_dir / "telegram.toml"

        # Create config with project pointing to non-existent path
        config = TelegramConfig(
            bot_token="test:token",
            projects=[
                TelegramProject(name="missing", path=tmp_path / "does_not_exist"),
            ],
        )
        save_config(config, config_path)

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@testbot"))),
        ):
            result = integration_runner.invoke(app, ["telegram", "doctor"])
            # Should succeed but with warnings
            assert result.exit_code == 0
            output = get_output(result)
            # Should warn about no allowed users and missing project path
            assert "No allowed users" in output
            assert "does not exist" in output


@pytest.mark.cli
class TestCommandSequencing:
    """Tests for correct command sequencing and state management."""

    def test_commands_before_init_fail_gracefully(
        self,
        integration_runner: CliRunner,
        config_dir: Path,
    ) -> None:
        """Test commands fail gracefully when config doesn't exist."""
        config_path = config_dir / "telegram.toml"

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            # projects list should fail
            result = integration_runner.invoke(app, ["telegram", "projects", "list"])
            assert result.exit_code == 1
            output = get_output(result)
            assert "Configuration not found" in output or "weld telegram init" in output

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
        ):
            # whoami should fail
            result = integration_runner.invoke(app, ["telegram", "whoami"])
            assert result.exit_code == 1
            output = get_output(result)
            assert "Configuration not found" in output or "weld telegram init" in output

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            # doctor should report config not found
            result = integration_runner.invoke(app, ["telegram", "doctor"])
            assert result.exit_code == 1
            assert "NOT FOUND" in get_output(result)

    def test_projects_add_requires_valid_path(
        self,
        integration_runner: CliRunner,
        config_dir: Path,
    ) -> None:
        """Test projects add validates path exists and is directory."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="test:token")
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            # Non-existent path
            result = integration_runner.invoke(
                app, ["telegram", "projects", "add", "proj", "/nonexistent/path"]
            )
            assert result.exit_code == 1
            assert "does not exist" in get_output(result)

            # File instead of directory
            file_path = config_dir / "afile.txt"
            file_path.write_text("content")
            result = integration_runner.invoke(
                app, ["telegram", "projects", "add", "proj", str(file_path)]
            )
            assert result.exit_code == 1
            assert "not a directory" in get_output(result)


@pytest.mark.cli
class TestMultipleProjectsWorkflow:
    """Tests for workflows involving multiple projects."""

    def test_multiple_projects_with_descriptions(
        self,
        integration_runner: CliRunner,
        config_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test adding multiple projects with various descriptions."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="test:token")
        save_config(config, config_path)

        # Create project directories
        dirs = [tmp_path / f"proj{i}" for i in range(3)]
        for d in dirs:
            d.mkdir()

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            # Add projects with different configurations
            result = integration_runner.invoke(
                app,
                ["telegram", "projects", "add", "api", str(dirs[0]), "-d", "API backend"],
            )
            assert result.exit_code == 0

            result = integration_runner.invoke(
                app,
                ["telegram", "projects", "add", "frontend", str(dirs[1])],  # No description
            )
            assert result.exit_code == 0

            result = integration_runner.invoke(
                app,
                ["telegram", "projects", "add", "shared", str(dirs[2]), "-d", "Shared libs"],
            )
            assert result.exit_code == 0

            # List all projects
            result = integration_runner.invoke(app, ["telegram", "projects", "list"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "api" in output
            assert "frontend" in output
            assert "shared" in output
            assert "API backend" in output
            assert "Shared libs" in output

        # Verify in config
        loaded = load_config(config_path)
        assert len(loaded.projects) == 3
        names = [p.name for p in loaded.projects]
        assert "api" in names
        assert "frontend" in names
        assert "shared" in names

    def test_duplicate_project_name_rejected(
        self,
        integration_runner: CliRunner,
        config_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test that duplicate project names are rejected."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="test:token")
        save_config(config, config_path)

        proj1 = tmp_path / "proj1"
        proj1.mkdir()
        proj2 = tmp_path / "proj2"
        proj2.mkdir()

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            # Add first project
            result = integration_runner.invoke(
                app, ["telegram", "projects", "add", "myapp", str(proj1)]
            )
            assert result.exit_code == 0

            # Try to add with same name but different path
            result = integration_runner.invoke(
                app, ["telegram", "projects", "add", "myapp", str(proj2)]
            )
            assert result.exit_code == 1
            assert "already exists" in get_output(result)
