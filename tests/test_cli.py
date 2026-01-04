"""CLI integration tests for weld."""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from weld.cli import app


class TestVersionCommand:
    """Tests for --version flag."""

    def test_version_shows_version(self, runner: CliRunner) -> None:
        """--version should display version string."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "weld" in result.stdout
        assert "0.1.0" in result.stdout

    def test_version_short_flag(self, runner: CliRunner) -> None:
        """-V should also display version."""
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0
        assert "weld" in result.stdout


class TestHelpCommand:
    """Tests for --help flag."""

    def test_help_shows_commands(self, runner: CliRunner) -> None:
        """--help should list all available commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "init" in result.stdout
        assert "run" in result.stdout
        assert "plan" in result.stdout
        assert "step" in result.stdout
        assert "commit" in result.stdout
        assert "list" in result.stdout

    def test_no_args_shows_help(self, runner: CliRunner) -> None:
        """Running with no args should show help (exit code 2 for no_args_is_help)."""
        result = runner.invoke(app, [])
        # Typer's no_args_is_help=True returns exit code 2
        assert result.exit_code == 2
        assert "Usage:" in result.stdout


class TestGlobalOptions:
    """Tests for global CLI options."""

    def test_verbose_flag_accepted(self, runner: CliRunner) -> None:
        """-v flag should be accepted."""
        result = runner.invoke(app, ["-v", "--help"])
        assert result.exit_code == 0

    def test_quiet_flag_accepted(self, runner: CliRunner) -> None:
        """-q flag should be accepted."""
        result = runner.invoke(app, ["-q", "--help"])
        assert result.exit_code == 0

    def test_json_flag_accepted(self, runner: CliRunner) -> None:
        """--json flag should be accepted."""
        result = runner.invoke(app, ["--json", "--help"])
        assert result.exit_code == 0

    def test_no_color_flag_accepted(self, runner: CliRunner) -> None:
        """--no-color flag should be accepted."""
        result = runner.invoke(app, ["--no-color", "--help"])
        assert result.exit_code == 0


class TestInitCommand:
    """Tests for weld init command."""

    def test_init_not_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """init should fail when not in a git repository."""
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(app, ["init"])
            assert result.exit_code == 3
            assert "Not a git repository" in result.stdout
        finally:
            os.chdir(original)

    def test_init_with_all_tools_present(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """init should succeed (exit 0) when all required tools are present."""

        def mock_subprocess_run(
            cmd: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            # Simulate all tools returning success
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("weld.commands.init.subprocess.run", side_effect=mock_subprocess_run):
            result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert "initialized successfully" in result.stdout.lower()

    def test_init_with_missing_tools(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """init should exit 2 when some required tools are missing."""

        def mock_subprocess_run(
            cmd: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            # Simulate codex not being installed (non-zero exit)
            if cmd[0] == "codex":
                raise FileNotFoundError("codex not found")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("weld.commands.init.subprocess.run", side_effect=mock_subprocess_run):
            result = runner.invoke(app, ["init"])

        assert result.exit_code == 2
        assert "codex" in result.stdout.lower()
        assert "not found" in result.stdout.lower()

    def test_init_already_initialized(self, runner: CliRunner, initialized_weld: Path) -> None:
        """init should handle already initialized directory (config exists)."""

        def mock_subprocess_run(
            cmd: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("weld.commands.init.subprocess.run", side_effect=mock_subprocess_run):
            result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert "already exists" in result.stdout.lower()


class TestListCommand:
    """Tests for weld list command."""

    def test_list_not_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """list should fail when not in a git repository."""
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 3
        finally:
            os.chdir(original)

    def test_list_no_runs(self, runner: CliRunner, initialized_weld: Path) -> None:
        """list should show message when no runs exist."""
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No runs found" in result.stdout

    def test_list_with_runs(self, runner: CliRunner, run_with_plan: tuple[Path, str]) -> None:
        """list should show existing runs."""
        _repo_root, run_id = run_with_plan
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert run_id in result.stdout


class TestRunCommand:
    """Tests for weld run command."""

    def test_run_not_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """run should fail with exit 3 when not in a git repository."""
        # Create spec file so we get past the spec-exists check
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test Spec\n")

        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(app, ["run", "--spec", "spec.md"])
            assert result.exit_code == 3
            assert "not a git repository" in result.stdout.lower()
        finally:
            os.chdir(original)

    def test_run_spec_not_found(self, runner: CliRunner, initialized_weld: Path) -> None:
        """run should fail when spec file doesn't exist."""
        result = runner.invoke(app, ["run", "--spec", "nonexistent.md"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_run_with_valid_spec(self, runner: CliRunner, initialized_weld: Path) -> None:
        """run should create run directory with valid spec."""
        spec_path = initialized_weld / "spec.md"
        spec_path.write_text("# Test Spec\n\nDo something useful.")

        result = runner.invoke(app, ["run", "--spec", str(spec_path)])
        assert result.exit_code == 0
        assert "Run created" in result.stdout

        # Verify run directory was created
        runs_dir = initialized_weld / ".weld" / "runs"
        runs = list(runs_dir.iterdir())
        assert len(runs) == 1


class TestPlanCommands:
    """Tests for weld plan subcommands."""

    def test_plan_help(self, runner: CliRunner) -> None:
        """plan --help should list subcommands."""
        result = runner.invoke(app, ["plan", "--help"])
        assert result.exit_code == 0
        assert "import" in result.stdout
        assert "review" in result.stdout

    def test_plan_import_missing_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """plan import should fail with nonexistent run."""
        plan_file = initialized_weld / "plan.md"
        plan_file.write_text("# Plan\n")
        result = runner.invoke(
            app, ["plan", "import", "--run", "nonexistent", "--file", str(plan_file)]
        )
        assert result.exit_code == 1

    def test_plan_review_missing_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """plan review should fail with nonexistent run."""
        result = runner.invoke(app, ["plan", "review", "--run", "nonexistent"])
        assert result.exit_code == 1


class TestStepCommands:
    """Tests for weld step subcommands."""

    def test_step_help(self, runner: CliRunner) -> None:
        """step --help should list subcommands."""
        result = runner.invoke(app, ["step", "--help"])
        assert result.exit_code == 0
        assert "select" in result.stdout
        assert "snapshot" in result.stdout
        assert "review" in result.stdout
        assert "loop" in result.stdout

    def test_step_select_missing_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """step select should fail with nonexistent run."""
        result = runner.invoke(app, ["step", "select", "--run", "nonexistent", "--n", "1"])
        assert result.exit_code != 0

    def test_step_select_valid_run(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """step select should work with valid run and step."""
        _repo_root, run_id = run_with_plan
        result = runner.invoke(app, ["step", "select", "--run", run_id, "--n", "1"])
        assert result.exit_code == 0
        assert "Selected step 1" in result.stdout

    def test_step_select_invalid_step_number(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """step select should fail with invalid step number."""
        _repo_root, run_id = run_with_plan
        result = runner.invoke(app, ["step", "select", "--run", run_id, "--n", "99"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()


class TestCommitCommand:
    """Tests for weld commit command."""

    def test_commit_not_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """commit should fail when not in a git repository."""
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(app, ["commit", "--run", "test", "-m", "test message"])
            assert result.exit_code == 3
        finally:
            os.chdir(original)

    def test_commit_missing_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """commit should fail with nonexistent run."""
        result = runner.invoke(app, ["commit", "--run", "nonexistent", "-m", "test message"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()


class TestTranscriptCommands:
    """Tests for weld transcript subcommands."""

    def test_transcript_help(self, runner: CliRunner) -> None:
        """transcript --help should list subcommands."""
        result = runner.invoke(app, ["transcript", "--help"])
        assert result.exit_code == 0
        assert "gist" in result.stdout


class TestErrorHandling:
    """Tests for error handling."""

    def test_invalid_subcommand(self, runner: CliRunner) -> None:
        """Invalid subcommand should show error."""
        result = runner.invoke(app, ["invalid-command"])
        assert result.exit_code != 0
