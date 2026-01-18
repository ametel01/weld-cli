"""CLI integration tests for Telegram bot commands."""

from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from weld.cli import app
from weld.telegram.config import (
    TelegramAuth,
    TelegramConfig,
    TelegramProject,
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
def telegram_runner() -> CliRunner:
    """Create CLI test runner with isolated environment for Telegram tests.

    Sets NO_COLOR for consistent output.
    """
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
def mock_aiogram() -> MagicMock:
    """Mock aiogram module to satisfy dependency check."""
    mock = MagicMock()
    return mock


def get_output(result: object) -> str:
    """Get combined stdout and output from result for assertion checking.

    Typer's CliRunner mixes stdout/stderr by default. This function
    extracts all text output from the result for assertion checking.
    """
    # Use output attribute if available (combines stdout/stderr)
    output = getattr(result, "output", None)
    if output:
        return output
    # Fallback to stdout if output not available
    return getattr(result, "stdout", "") or ""


@pytest.mark.cli
class TestTelegramHelp:
    """Tests for telegram command help."""

    def test_telegram_help(self, telegram_runner: CliRunner) -> None:
        """weld telegram --help should show subcommands."""
        result = telegram_runner.invoke(app, ["telegram", "--help"])
        assert result.exit_code == 0
        output = get_output(result)
        assert "init" in output
        assert "whoami" in output
        assert "doctor" in output
        assert "projects" in output
        assert "user" in output
        assert "serve" in output

    def test_telegram_no_args(self, telegram_runner: CliRunner) -> None:
        """weld telegram with no args shows help (no_args_is_help=True)."""
        result = telegram_runner.invoke(app, ["telegram"])
        # no_args_is_help=True with typer returns exit code 0 and shows help
        # But typer might return exit code 2 for help text - either is acceptable
        output = get_output(result)
        assert "init" in output


@pytest.mark.cli
class TestTelegramInit:
    """Tests for weld telegram init command."""

    def test_init_invalid_token_format(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """init should fail with invalid token format."""
        with (
            patch(
                "weld.telegram.config.get_config_path",
                return_value=config_dir / "telegram.toml",
            ),
        ):
            result = telegram_runner.invoke(app, ["telegram", "init", "-t", "invalid-token"])
            assert result.exit_code == 1
            output = get_output(result)
            assert "Invalid token format" in output

    def test_init_empty_token(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """init should fail with empty token."""
        with (
            patch(
                "weld.telegram.config.get_config_path",
                return_value=config_dir / "telegram.toml",
            ),
        ):
            result = telegram_runner.invoke(app, ["telegram", "init", "-t", "   "])
            assert result.exit_code == 1
            output = get_output(result)
            assert "Token cannot be empty" in output

    def test_init_token_validation_fails(
        self, telegram_runner: CliRunner, config_dir: Path
    ) -> None:
        """init should fail when token validation fails."""
        with (
            patch(
                "weld.telegram.config.get_config_path",
                return_value=config_dir / "telegram.toml",
            ),
            patch(
                "asyncio.run",
                side_effect=mock_asyncio_run((False, "Invalid token: unauthorized")),
            ),
        ):
            result = telegram_runner.invoke(app, ["telegram", "init", "-t", "123:ABC"])
            assert result.exit_code == 1
            output = get_output(result)
            # The error message can be in stdout or stderr
            assert "Invalid token" in output or "unauthorized" in output

    def test_init_success(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """init should succeed with valid token."""
        config_path = config_dir / "telegram.toml"

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@testbot"))),
        ):
            result = telegram_runner.invoke(app, ["telegram", "init", "-t", "123:ABC"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "Token valid" in output
            assert "@testbot" in output
            assert config_path.exists()

    def test_init_config_exists_without_force(
        self, telegram_runner: CliRunner, config_dir: Path
    ) -> None:
        """init should fail if config exists without --force."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="existing:token")
        save_config(config, config_path)

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
        ):
            result = telegram_runner.invoke(app, ["telegram", "init", "-t", "new:token"])
            assert result.exit_code == 1
            output = get_output(result)
            assert "already exists" in output
            assert "--force" in output

    def test_init_config_exists_with_force(
        self, telegram_runner: CliRunner, config_dir: Path
    ) -> None:
        """init should overwrite config with --force."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="old:token")
        save_config(config, config_path)

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@newbot"))),
        ):
            result = telegram_runner.invoke(app, ["telegram", "init", "-t", "new:token", "--force"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "@newbot" in output

    def test_init_prompts_global_install_when_not_available(
        self, telegram_runner: CliRunner, config_dir: Path
    ) -> None:
        """init should prompt to install weld globally when not in PATH."""
        config_path = config_dir / "telegram.toml"

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@testbot"))),
            patch("weld.telegram.cli._is_weld_globally_available", return_value=False),
        ):
            # Answer 'n' to the install prompt
            result = telegram_runner.invoke(app, ["telegram", "init", "-t", "123:ABC"], input="n\n")
            assert result.exit_code == 0
            output = get_output(result)
            assert "not available globally" in output
            assert "Install weld globally" in output

    def test_init_skips_prompt_when_weld_available(
        self, telegram_runner: CliRunner, config_dir: Path
    ) -> None:
        """init should not prompt when weld is already globally available."""
        config_path = config_dir / "telegram.toml"

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@testbot"))),
            patch("weld.telegram.cli._is_weld_globally_available", return_value=True),
        ):
            result = telegram_runner.invoke(app, ["telegram", "init", "-t", "123:ABC"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "not available globally" not in output

    def test_init_installs_globally_when_confirmed(
        self, telegram_runner: CliRunner, config_dir: Path
    ) -> None:
        """init should install weld globally when user confirms."""
        config_path = config_dir / "telegram.toml"

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@testbot"))),
            patch("weld.telegram.cli._is_weld_globally_available", return_value=False),
            patch("weld.telegram.cli._install_weld_globally", return_value=True) as mock_install,
        ):
            # Answer 'y' to the install prompt
            result = telegram_runner.invoke(app, ["telegram", "init", "-t", "123:ABC"], input="y\n")
            assert result.exit_code == 0
            mock_install.assert_called_once()


@pytest.mark.cli
class TestTelegramWhoami:
    """Tests for weld telegram whoami command."""

    def test_whoami_no_config(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """whoami should fail when config doesn't exist."""
        config_path = config_dir / "telegram.toml"

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
        ):
            result = telegram_runner.invoke(app, ["telegram", "whoami"])
            assert result.exit_code == 1
            output = get_output(result)
            # The error mentions running init, or mentions config not found
            assert "weld telegram init" in output or "Configuration not found" in output

    def test_whoami_no_token(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """whoami should fail when token is not set."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig()  # No token
        save_config(config, config_path)

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
        ):
            result = telegram_runner.invoke(app, ["telegram", "whoami"])
            assert result.exit_code == 1
            output = get_output(result)
            # Error mentions token not set or running init
            assert "Token not set" in output or "weld telegram init" in output

    def test_whoami_invalid_token(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """whoami should fail when token validation fails."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="invalid:token")
        save_config(config, config_path)

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch(
                "asyncio.run",
                side_effect=mock_asyncio_run((False, "Invalid token: unauthorized")),
            ),
        ):
            result = telegram_runner.invoke(app, ["telegram", "whoami"])
            assert result.exit_code == 1
            output = get_output(result)
            assert "Invalid token" in output or "unauthorized" in output

    def test_whoami_success(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """whoami should show bot info when authenticated."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(
            bot_token="valid:token",
            auth=TelegramAuth(allowed_user_ids=[12345], allowed_usernames=["alice"]),
            projects=[TelegramProject(name="proj1", path=config_dir)],
        )
        save_config(config, config_path)

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@mybot"))),
        ):
            result = telegram_runner.invoke(app, ["telegram", "whoami"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "Status: Authenticated" in output
            assert "Bot: @mybot" in output
            assert "Allowed users: 1 IDs, 1 usernames" in output
            assert "Projects: 1 registered" in output


@pytest.mark.cli
class TestTelegramDoctor:
    """Tests for weld telegram doctor command."""

    def test_doctor_no_config(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """doctor should report missing config."""
        config_path = config_dir / "telegram.toml"

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "doctor"])
            assert result.exit_code == 1
            output = get_output(result)
            assert "NOT FOUND" in output
            assert "weld telegram init" in output

    def test_doctor_invalid_config(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """doctor should report invalid config."""
        config_path = config_dir / "telegram.toml"
        config_path.write_text("invalid [ toml")

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "doctor"])
            assert result.exit_code == 1
            output = get_output(result)
            assert "INVALID" in output

    def test_doctor_no_token(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """doctor should report missing token."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig()  # No token
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "doctor"])
            assert result.exit_code == 1
            output = get_output(result)
            assert "NOT SET" in output

    def test_doctor_no_users(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """doctor should warn about no allowed users."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="valid:token")
        save_config(config, config_path)

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@mybot"))),
        ):
            result = telegram_runner.invoke(app, ["telegram", "doctor"])
            # Exit 0 because warnings don't cause failure
            assert result.exit_code == 0
            output = get_output(result)
            assert "No allowed users" in output

    def test_doctor_no_projects(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """doctor should warn about no projects."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(
            bot_token="valid:token",
            auth=TelegramAuth(allowed_user_ids=[12345]),
        )
        save_config(config, config_path)

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@mybot"))),
        ):
            result = telegram_runner.invoke(app, ["telegram", "doctor"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "No projects registered" in output

    def test_doctor_project_path_not_exists(
        self, telegram_runner: CliRunner, config_dir: Path
    ) -> None:
        """doctor should warn about non-existent project paths."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(
            bot_token="valid:token",
            auth=TelegramAuth(allowed_user_ids=[12345]),
            projects=[TelegramProject(name="missing", path=config_dir / "nonexistent")],
        )
        save_config(config, config_path)

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@mybot"))),
        ):
            result = telegram_runner.invoke(app, ["telegram", "doctor"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "does not exist" in output

    def test_doctor_all_checks_pass(
        self, telegram_runner: CliRunner, config_dir: Path, tmp_path: Path
    ) -> None:
        """doctor should pass when everything is configured correctly."""
        config_path = config_dir / "telegram.toml"
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()

        config = TelegramConfig(
            bot_token="valid:token",
            auth=TelegramAuth(allowed_user_ids=[12345]),
            projects=[TelegramProject(name="myproject", path=project_dir)],
        )
        save_config(config, config_path)

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@mybot"))),
        ):
            result = telegram_runner.invoke(app, ["telegram", "doctor"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "All checks passed" in output


@pytest.mark.cli
class TestTelegramProjects:
    """Tests for weld telegram projects subcommands."""

    def test_projects_help(self, telegram_runner: CliRunner) -> None:
        """weld telegram projects --help should show subcommands."""
        result = telegram_runner.invoke(app, ["telegram", "projects", "--help"])
        assert result.exit_code == 0
        output = get_output(result)
        assert "add" in output
        assert "remove" in output
        assert "list" in output

    def test_projects_list_no_config(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """projects list should fail when config doesn't exist."""
        config_path = config_dir / "telegram.toml"

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "projects", "list"])
            assert result.exit_code == 1
            output = get_output(result)
            # Error mentions config not found or running init
            assert "Configuration not found" in output or "weld telegram init" in output

    def test_projects_list_empty(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """projects list should show message when no projects."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="test:token")
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "projects", "list"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "No projects registered" in output

    def test_projects_list_with_projects(
        self, telegram_runner: CliRunner, config_dir: Path, tmp_path: Path
    ) -> None:
        """projects list should show all registered projects."""
        config_path = config_dir / "telegram.toml"
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()

        config = TelegramConfig(
            bot_token="test:token",
            projects=[
                TelegramProject(name="myproject", path=project_dir, description="Test project")
            ],
        )
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "projects", "list"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "myproject" in output
            assert str(project_dir) in output
            assert "Test project" in output

    def test_projects_add_path_not_exists(
        self, telegram_runner: CliRunner, config_dir: Path
    ) -> None:
        """projects add should fail when path doesn't exist."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="test:token")
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(
                app, ["telegram", "projects", "add", "newproj", "/nonexistent/path"]
            )
            assert result.exit_code == 1
            output = get_output(result)
            assert "does not exist" in output

    def test_projects_add_path_not_directory(
        self, telegram_runner: CliRunner, config_dir: Path, tmp_path: Path
    ) -> None:
        """projects add should fail when path is not a directory."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="test:token")
        save_config(config, config_path)

        file_path = tmp_path / "afile.txt"
        file_path.write_text("content")

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(
                app, ["telegram", "projects", "add", "newproj", str(file_path)]
            )
            assert result.exit_code == 1
            output = get_output(result)
            assert "not a directory" in output

    def test_projects_add_duplicate_name(
        self, telegram_runner: CliRunner, config_dir: Path, tmp_path: Path
    ) -> None:
        """projects add should fail when project name already exists."""
        config_path = config_dir / "telegram.toml"
        project_dir = tmp_path / "existing"
        project_dir.mkdir()
        new_dir = tmp_path / "new"
        new_dir.mkdir()

        config = TelegramConfig(
            bot_token="test:token",
            projects=[TelegramProject(name="myproj", path=project_dir)],
        )
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(
                app, ["telegram", "projects", "add", "myproj", str(new_dir)]
            )
            assert result.exit_code == 1
            output = get_output(result)
            assert "already exists" in output

    def test_projects_add_success(
        self, telegram_runner: CliRunner, config_dir: Path, tmp_path: Path
    ) -> None:
        """projects add should succeed with valid inputs."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="test:token")
        save_config(config, config_path)

        project_dir = tmp_path / "myproject"
        project_dir.mkdir()

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(
                app,
                [
                    "telegram",
                    "projects",
                    "add",
                    "myproject",
                    str(project_dir),
                    "-d",
                    "My test project",
                ],
            )
            assert result.exit_code == 0
            output = get_output(result)
            assert "Added project" in output
            assert "myproject" in output

        # Verify project was persisted
        from weld.telegram.config import load_config

        loaded = load_config(config_path)
        assert len(loaded.projects) == 1
        assert loaded.projects[0].name == "myproject"
        assert loaded.projects[0].description == "My test project"

    def test_projects_remove_not_found(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """projects remove should fail when project doesn't exist."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="test:token")
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "projects", "remove", "nonexistent"])
            assert result.exit_code == 1
            output = get_output(result)
            # Error mentions not found or suggests listing projects
            assert "not found" in output or "projects list" in output

    def test_projects_remove_success(
        self, telegram_runner: CliRunner, config_dir: Path, tmp_path: Path
    ) -> None:
        """projects remove should successfully remove project."""
        config_path = config_dir / "telegram.toml"
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()

        config = TelegramConfig(
            bot_token="test:token",
            projects=[TelegramProject(name="myproject", path=project_dir)],
        )
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "projects", "remove", "myproject"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "Removed project" in output

        # Verify project was removed
        from weld.telegram.config import load_config

        loaded = load_config(config_path)
        assert len(loaded.projects) == 0


@pytest.mark.cli
class TestEnvironmentIsolation:
    """Tests to verify environment variable isolation between tests."""

    def test_config_path_isolation_a(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """First test in pair - sets up config in temp dir A."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(
            bot_token="test:token_a",
            auth=TelegramAuth(allowed_user_ids=[111]),
        )
        save_config(config, config_path)

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@bot_a"))),
        ):
            result = telegram_runner.invoke(app, ["telegram", "whoami"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "@bot_a" in output
            assert "1 IDs" in output

    def test_config_path_isolation_b(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """Second test in pair - sets up different config in temp dir B."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(
            bot_token="test:token_b",
            auth=TelegramAuth(allowed_user_ids=[222, 333]),
        )
        save_config(config, config_path)

        with (
            patch("weld.telegram.config.get_config_path", return_value=config_path),
            patch("asyncio.run", side_effect=mock_asyncio_run((True, "@bot_b"))),
        ):
            result = telegram_runner.invoke(app, ["telegram", "whoami"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "@bot_b" in output
            assert "2 IDs" in output

    def test_no_real_home_dir_access(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """Verify tests don't access real home directory config."""
        # This test verifies that our mocking of get_config_path
        # prevents tests from accessing the real ~/.config/weld/telegram.toml
        config_path = config_dir / "telegram.toml"

        # Config doesn't exist in our temp dir
        assert not config_path.exists()

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "projects", "list"])
            # Should fail because config doesn't exist in temp dir
            assert result.exit_code == 1
            output = get_output(result)
            # Error mentions config not found or running init
            assert "Configuration not found" in output or "weld telegram init" in output


@pytest.mark.cli
class TestTelegramUser:
    """Tests for weld telegram user subcommands."""

    def test_user_help(self, telegram_runner: CliRunner) -> None:
        """weld telegram user --help should show subcommands."""
        result = telegram_runner.invoke(app, ["telegram", "user", "--help"])
        assert result.exit_code == 0
        output = get_output(result)
        assert "add" in output
        assert "remove" in output
        assert "list" in output

    def test_user_list_no_config(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """user list should fail when config doesn't exist."""
        config_path = config_dir / "telegram.toml"

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "user", "list"])
            assert result.exit_code == 1
            output = get_output(result)
            assert "Configuration not found" in output or "weld telegram init" in output

    def test_user_list_empty(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """user list should show message when no users."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="test:token")
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "user", "list"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "No users in allowlist" in output

    def test_user_list_with_users(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """user list should show all allowed users."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(
            bot_token="test:token",
            auth=TelegramAuth(allowed_user_ids=[12345, 67890], allowed_usernames=["alice", "bob"]),
        )
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "user", "list"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "12345" in output
            assert "67890" in output
            assert "@alice" in output
            assert "@bob" in output

    def test_user_add_by_id(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """user add should add user by numeric ID."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="test:token")
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "user", "add", "12345"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "Added user ID 12345" in output

        # Verify user was persisted
        from weld.telegram.config import load_config

        loaded = load_config(config_path)
        assert 12345 in loaded.auth.allowed_user_ids

    def test_user_add_by_username(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """user add should add user by username."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="test:token")
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "user", "add", "alice"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "Added username 'alice'" in output

        # Verify user was persisted
        from weld.telegram.config import load_config

        loaded = load_config(config_path)
        assert "alice" in loaded.auth.allowed_usernames

    def test_user_add_strips_at_prefix(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """user add should strip @ prefix from usernames."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="test:token")
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "user", "add", "@alice"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "Added username 'alice'" in output

        # Verify username stored without @
        from weld.telegram.config import load_config

        loaded = load_config(config_path)
        assert "alice" in loaded.auth.allowed_usernames
        assert "@alice" not in loaded.auth.allowed_usernames

    def test_user_add_duplicate_id(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """user add should not add duplicate user ID."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(
            bot_token="test:token",
            auth=TelegramAuth(allowed_user_ids=[12345]),
        )
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "user", "add", "12345"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "already in the allowlist" in output

    def test_user_add_duplicate_username(
        self, telegram_runner: CliRunner, config_dir: Path
    ) -> None:
        """user add should not add duplicate username."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(
            bot_token="test:token",
            auth=TelegramAuth(allowed_usernames=["alice"]),
        )
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "user", "add", "alice"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "already in the allowlist" in output

    def test_user_remove_id_success(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """user remove should remove user by ID."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(
            bot_token="test:token",
            auth=TelegramAuth(allowed_user_ids=[12345, 67890]),
        )
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "user", "remove", "12345"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "Removed user ID 12345" in output

        # Verify user was removed
        from weld.telegram.config import load_config

        loaded = load_config(config_path)
        assert 12345 not in loaded.auth.allowed_user_ids
        assert 67890 in loaded.auth.allowed_user_ids

    def test_user_remove_username_success(
        self, telegram_runner: CliRunner, config_dir: Path
    ) -> None:
        """user remove should remove user by username."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(
            bot_token="test:token",
            auth=TelegramAuth(allowed_usernames=["alice", "bob"]),
        )
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "user", "remove", "alice"])
            assert result.exit_code == 0
            output = get_output(result)
            assert "Removed username 'alice'" in output

        # Verify user was removed
        from weld.telegram.config import load_config

        loaded = load_config(config_path)
        assert "alice" not in loaded.auth.allowed_usernames
        assert "bob" in loaded.auth.allowed_usernames

    def test_user_remove_id_not_found(self, telegram_runner: CliRunner, config_dir: Path) -> None:
        """user remove should fail when user ID not found."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="test:token")
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "user", "remove", "99999"])
            assert result.exit_code == 1
            output = get_output(result)
            assert "not found" in output

    def test_user_remove_username_not_found(
        self, telegram_runner: CliRunner, config_dir: Path
    ) -> None:
        """user remove should fail when username not found."""
        config_path = config_dir / "telegram.toml"
        config = TelegramConfig(bot_token="test:token")
        save_config(config, config_path)

        with patch("weld.telegram.config.get_config_path", return_value=config_path):
            result = telegram_runner.invoke(app, ["telegram", "user", "remove", "nobody"])
            assert result.exit_code == 1
            output = get_output(result)
            assert "not found" in output
