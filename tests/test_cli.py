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
        assert "research" in result.stdout
        assert "discover" in result.stdout
        assert "interview" in result.stdout
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

    def test_dry_run_flag_accepted(self, runner: CliRunner) -> None:
        """--dry-run flag should be accepted."""
        result = runner.invoke(app, ["--dry-run", "--help"])
        assert result.exit_code == 0

    def test_debug_flag_accepted(self, runner: CliRunner) -> None:
        """--debug flag should be accepted."""
        result = runner.invoke(app, ["--debug", "--help"])
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

    def test_init_dry_run_no_side_effects(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """init --dry-run should not create any directories or files."""
        weld_dir = temp_git_repo / ".weld"
        assert not weld_dir.exists()

        result = runner.invoke(app, ["--dry-run", "init"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        # Verify no directories were created
        assert not weld_dir.exists()


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

    def test_run_dry_run_no_side_effects(self, runner: CliRunner, initialized_weld: Path) -> None:
        """run --dry-run should not create run directory."""
        spec_path = initialized_weld / "spec.md"
        spec_path.write_text("# Test Spec\n\nDo something useful.")

        runs_dir = initialized_weld / ".weld" / "runs"
        runs_before = list(runs_dir.iterdir()) if runs_dir.exists() else []

        result = runner.invoke(app, ["--dry-run", "run", "--spec", str(spec_path)])
        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout

        # Verify no new run directories were created
        runs_after = list(runs_dir.iterdir()) if runs_dir.exists() else []
        assert len(runs_after) == len(runs_before)

    def test_run_with_skip_research(self, runner: CliRunner, initialized_weld: Path) -> None:
        """run --skip-research should create plan prompt directly."""
        spec_path = initialized_weld / "spec.md"
        spec_path.write_text("# Test Spec\n\nDo something useful.")

        result = runner.invoke(app, ["run", "--spec", str(spec_path), "--skip-research"])
        assert result.exit_code == 0
        assert "Run created" in result.stdout

        # Verify run directory was created without research dir
        runs_dir = initialized_weld / ".weld" / "runs"
        runs = list(runs_dir.iterdir())
        assert len(runs) == 1
        run_dir = runs[0]

        # Should have plan dir but not research dir
        assert (run_dir / "plan").exists()
        assert (run_dir / "plan" / "plan.prompt.md").exists()
        assert not (run_dir / "research").exists()

    def test_run_default_creates_research_dir(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """run without --skip-research should create research directory."""
        spec_path = initialized_weld / "spec.md"
        spec_path.write_text("# Test Spec\n\nDo something useful.")

        result = runner.invoke(app, ["run", "--spec", str(spec_path)])
        assert result.exit_code == 0
        assert "Run created" in result.stdout

        # Verify research directory was created
        runs_dir = initialized_weld / ".weld" / "runs"
        runs = list(runs_dir.iterdir())
        assert len(runs) == 1
        run_dir = runs[0]

        # Should have research dir with prompt
        assert (run_dir / "research").exists()
        assert (run_dir / "research" / "prompt.md").exists()


class TestResearchCommands:
    """Tests for weld research subcommands."""

    def test_research_help(self, runner: CliRunner) -> None:
        """research --help should list subcommands."""
        result = runner.invoke(app, ["research", "--help"])
        assert result.exit_code == 0
        assert "prompt" in result.stdout
        assert "import" in result.stdout
        assert "show" in result.stdout

    def test_research_prompt_missing_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """research prompt should fail with nonexistent run."""
        result = runner.invoke(app, ["research", "prompt", "--run", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_research_import_missing_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """research import should fail with nonexistent run."""
        research_file = initialized_weld / "research.md"
        research_file.write_text("# Research\n")
        result = runner.invoke(
            app, ["research", "import", "--run", "nonexistent", "--file", str(research_file)]
        )
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_research_show_missing_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """research show should fail with nonexistent run."""
        result = runner.invoke(app, ["research", "show", "--run", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_research_show_skip_research_run(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """research show should fail with helpful error for skip-research runs."""
        spec_path = initialized_weld / "spec.md"
        spec_path.write_text("# Test Spec\n")

        # Create run with --skip-research
        result = runner.invoke(app, ["run", "--spec", str(spec_path), "--skip-research"])
        assert result.exit_code == 0

        # Get run ID from output
        runs_dir = initialized_weld / ".weld" / "runs"
        runs = list(runs_dir.iterdir())
        run_id = runs[0].name

        # Try to show research - should fail with clear error
        result = runner.invoke(app, ["research", "show", "--run", run_id])
        assert result.exit_code == 1
        assert "skip-research" in result.stdout.lower()


class TestPlanCommands:
    """Tests for weld plan subcommands."""

    def test_plan_help(self, runner: CliRunner) -> None:
        """plan --help should list subcommands."""
        result = runner.invoke(app, ["plan", "--help"])
        assert result.exit_code == 0
        assert "prompt" in result.stdout
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


class TestResearchVersioning:
    """Tests for research import versioning."""

    def test_research_import_creates_version_on_reimport(
        self, runner: CliRunner, run_with_research: tuple[Path, str]
    ) -> None:
        """Re-importing research should create a version snapshot."""
        repo_root, run_id = run_with_research
        weld_dir = repo_root / ".weld"
        run_dir = weld_dir / "runs" / run_id

        # Create new research file to import
        new_research = repo_root / "new_research.md"
        new_research.write_text("# Updated Research\n\nNew findings.")

        # Import new research (should version the old one)
        result = runner.invoke(
            app, ["research", "import", "--run", run_id, "--file", str(new_research)]
        )

        assert result.exit_code == 0
        assert "Previous research saved as v1" in result.stdout

        # Verify version was created
        history_dir = run_dir / "research" / "history"
        assert history_dir.exists()
        assert (history_dir / "v1").exists()
        assert (history_dir / "v1" / "content.md").exists()

        # Verify old content was preserved
        old_content = (history_dir / "v1" / "content.md").read_text()
        assert "Initial Research" in old_content

        # Verify new content is current
        current = (run_dir / "research" / "research.md").read_text()
        assert "Updated Research" in current

    def test_research_import_updates_meta_version(
        self, runner: CliRunner, run_with_research: tuple[Path, str]
    ) -> None:
        """Re-importing research should update research_version in meta.json."""
        repo_root, run_id = run_with_research
        weld_dir = repo_root / ".weld"
        run_dir = weld_dir / "runs" / run_id

        from weld.models import Meta

        # Check initial version
        meta_before = Meta.model_validate_json((run_dir / "meta.json").read_text())
        assert meta_before.research_version == 1

        # Create and import new research
        new_research = repo_root / "new_research.md"
        new_research.write_text("# Updated Research")

        result = runner.invoke(
            app, ["research", "import", "--run", run_id, "--file", str(new_research)]
        )
        assert result.exit_code == 0

        # Check version was incremented
        meta_after = Meta.model_validate_json((run_dir / "meta.json").read_text())
        assert meta_after.research_version == 2

    def test_research_import_dry_run_no_versioning(
        self, runner: CliRunner, run_with_research: tuple[Path, str]
    ) -> None:
        """Dry-run research import should not create version snapshots."""
        repo_root, run_id = run_with_research
        weld_dir = repo_root / ".weld"
        run_dir = weld_dir / "runs" / run_id

        new_research = repo_root / "new_research.md"
        new_research.write_text("# Updated Research")

        result = runner.invoke(
            app,
            ["--dry-run", "research", "import", "--run", run_id, "--file", str(new_research)],
        )

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "would be versioned" in result.stdout

        # Verify no version was created
        history_dir = run_dir / "research" / "history"
        assert not history_dir.exists()


class TestPlanVersioning:
    """Tests for plan import versioning."""

    def test_plan_import_creates_version_on_reimport(
        self, runner: CliRunner, run_with_plan: tuple[Path, str], sample_plan: str
    ) -> None:
        """Re-importing plan should create a version snapshot."""
        repo_root, run_id = run_with_plan
        weld_dir = repo_root / ".weld"
        run_dir = weld_dir / "runs" / run_id

        # Create new plan file to import
        new_plan = repo_root / "new_plan.md"
        new_plan.write_text("## Step 1: New Implementation\n\n### Goal\nDo new thing.\n")

        # Import new plan (should version the old one)
        result = runner.invoke(app, ["plan", "import", "--run", run_id, "--file", str(new_plan)])

        assert result.exit_code == 0
        assert "Previous plan saved as v1" in result.stdout

        # Verify version was created
        history_dir = run_dir / "plan" / "history"
        assert history_dir.exists()
        assert (history_dir / "v1").exists()
        assert (history_dir / "v1" / "content.md").exists()

        # Verify old content was preserved
        old_content = (history_dir / "v1" / "content.md").read_text()
        assert "Create hello module" in old_content  # from sample_plan

    def test_plan_import_dry_run_no_versioning(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """Dry-run plan import should not create version snapshots."""
        repo_root, run_id = run_with_plan
        weld_dir = repo_root / ".weld"
        run_dir = weld_dir / "runs" / run_id

        new_plan = repo_root / "new_plan.md"
        new_plan.write_text("## Step 1: New\n\n### Goal\nNew thing.\n")

        result = runner.invoke(
            app, ["--dry-run", "plan", "import", "--run", run_id, "--file", str(new_plan)]
        )

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "would be versioned" in result.stdout

        # Verify no version was created
        history_dir = run_dir / "plan" / "history"
        assert not history_dir.exists()


class TestDiscoverCommands:
    """Tests for weld discover command."""

    def test_discover_help(self, runner: CliRunner) -> None:
        """discover --help should show options and subcommands."""
        result = runner.invoke(app, ["discover", "--help"])
        assert result.exit_code == 0
        assert "--output" in result.stdout
        assert "list" in result.stdout
        assert "show" in result.stdout

    def test_discover_not_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """discover should fail when not in a git repository."""
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(app, ["discover", "--output", "out.md"])
            assert result.exit_code == 3
            assert "Not a git repository" in result.stdout
        finally:
            os.chdir(original)

    def test_discover_creates_artifact(self, runner: CliRunner, initialized_weld: Path) -> None:
        """discover should create discover artifact with prompt.md and meta.json."""
        result = runner.invoke(app, ["discover", "--output", "arch.md", "--prompt-only"])
        assert result.exit_code == 0
        assert "Discover run:" in result.stdout
        assert "prompt.md" in result.stdout

        # Verify discover directory was created
        discover_dir = initialized_weld / ".weld" / "discover"
        assert discover_dir.exists()
        artifacts = list(discover_dir.iterdir())
        assert len(artifacts) == 1

        artifact_dir = artifacts[0]
        # Verify both prompt.md and meta.json exist
        assert (artifact_dir / "prompt.md").exists()
        assert (artifact_dir / "meta.json").exists()

        # Verify meta.json has expected structure
        import json

        meta = json.loads((artifact_dir / "meta.json").read_text())
        assert "discover_id" in meta
        assert "config_hash" in meta
        assert meta["output_path"] == "arch.md"
        assert meta["partial"] is False

    def test_discover_with_focus(self, runner: CliRunner, initialized_weld: Path) -> None:
        """discover --focus should include focus in prompt."""
        result = runner.invoke(
            app,
            ["discover", "--output", "arch.md", "--focus", "API layer", "--prompt-only"],
        )
        assert result.exit_code == 0

        # Check prompt content
        discover_dir = initialized_weld / ".weld" / "discover"
        artifacts = list(discover_dir.iterdir())
        prompt_content = (artifacts[0] / "prompt.md").read_text()
        assert "API layer" in prompt_content

    def test_discover_dry_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """discover --dry-run should not create artifacts."""
        result = runner.invoke(app, ["--dry-run", "discover", "--output", "arch.md"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout

        # Verify no discover directory was created
        discover_dir = initialized_weld / ".weld" / "discover"
        assert not discover_dir.exists()

    def test_discover_list_empty(self, runner: CliRunner, initialized_weld: Path) -> None:
        """discover list should show message when no artifacts exist."""
        result = runner.invoke(app, ["discover", "list"])
        assert result.exit_code == 0
        assert "No discover artifacts found" in result.stdout

    def test_discover_list_with_artifacts(self, runner: CliRunner, initialized_weld: Path) -> None:
        """discover list should show existing artifacts with their IDs."""
        # Create a discover artifact
        runner.invoke(app, ["discover", "--output", "out.md", "--prompt-only"])

        result = runner.invoke(app, ["discover", "list"])
        assert result.exit_code == 0
        assert "Discover artifacts:" in result.stdout

        # Verify the artifact ID format is shown (YYYYMMDD-HHMMSS-discover)
        import re

        assert re.search(r"\d{8}-\d{6}-discover", result.stdout) is not None
        # Verify status indicator is shown
        assert "ready" in result.stdout.lower()

    def test_discover_show_missing(self, runner: CliRunner, initialized_weld: Path) -> None:
        """discover show should fail when no artifacts exist."""
        result = runner.invoke(app, ["discover", "show"])
        assert result.exit_code == 1
        assert "No discover artifacts found" in result.stdout

    def test_discover_show_displays_prompt(self, runner: CliRunner, initialized_weld: Path) -> None:
        """discover show should display prompt content."""
        # Create a discover artifact
        runner.invoke(app, ["discover", "--output", "out.md", "--prompt-only"])

        result = runner.invoke(app, ["discover", "show"])
        assert result.exit_code == 0
        assert "System Architecture" in result.stdout


class TestInterviewCommand:
    """Tests for weld interview command."""

    def test_interview_help(self, runner: CliRunner) -> None:
        """interview --help should show usage."""
        result = runner.invoke(app, ["interview", "--help"])
        assert result.exit_code == 0
        assert "file" in result.stdout.lower()
        assert "focus" in result.stdout.lower()

    def test_interview_file_not_found(self, runner: CliRunner, initialized_weld: Path) -> None:
        """interview should fail when file doesn't exist."""
        result = runner.invoke(app, ["interview", "nonexistent.md"])
        assert result.exit_code == 1
        assert "File not found" in result.stdout

    def test_interview_non_markdown_warning(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """interview should warn for non-markdown files."""
        # Create a non-markdown file
        txt_file = initialized_weld / "spec.txt"
        txt_file.write_text("Some content")

        # Run with input that immediately quits
        result = runner.invoke(app, ["interview", str(txt_file)], input="quit\n")
        assert result.exit_code == 0
        assert "not markdown" in result.stdout.lower()

    def test_interview_dry_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """interview --dry-run should not modify file."""
        spec_file = initialized_weld / "spec.md"
        original_content = "# My Spec\n\nOriginal content."
        spec_file.write_text(original_content)

        result = runner.invoke(app, ["--dry-run", "interview", str(spec_file)])
        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        # File should be unchanged
        assert spec_file.read_text() == original_content

    def test_interview_records_answers(self, runner: CliRunner, initialized_weld: Path) -> None:
        """interview should record answers and modify document."""
        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# My Spec")

        # Provide an answer then quit with save
        result = runner.invoke(
            app,
            ["interview", str(spec_file)],
            input="This is my answer\nquit\ny\n",
        )
        assert result.exit_code == 0

        content = spec_file.read_text()
        assert "This is my answer" in content
        assert "## Interview Notes" in content


class TestStatusCommand:
    """Tests for weld status command."""

    def test_status_help(self, runner: CliRunner) -> None:
        """status --help should show usage."""
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0
        assert "--run" in result.stdout

    def test_status_not_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """status should fail when not in a git repository."""
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(app, ["status"])
            assert result.exit_code == 3
            assert "Not a git repository" in result.stdout
        finally:
            os.chdir(original)

    def test_status_no_runs(self, runner: CliRunner, initialized_weld: Path) -> None:
        """status should show error when no runs exist."""
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1
        assert "No runs found" in result.stdout

    def test_status_nonexistent_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """status should show error for nonexistent run."""
        result = runner.invoke(app, ["status", "--run", "nonexistent"])
        assert result.exit_code == 1
        assert "Run not found" in result.stdout

    def test_status_shows_run_info(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """status should show run information."""
        _repo_root, run_id = run_with_plan
        result = runner.invoke(app, ["status", "--run", run_id])
        assert result.exit_code == 0
        assert run_id in result.stdout
        assert "Branch:" in result.stdout

    def test_status_shows_next_step_with_correct_syntax(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """status should show correct next command with --n parameter."""
        repo_root, run_id = run_with_plan
        # Set up steps directory with an incomplete step
        steps_dir = repo_root / ".weld" / "runs" / run_id / "steps"
        steps_dir.mkdir(exist_ok=True)
        (steps_dir / "01-create-hello-module").mkdir()

        result = runner.invoke(app, ["status", "--run", run_id])
        assert result.exit_code == 0
        # Verify correct syntax: --n 1, not --step 01-create-hello-module
        assert "--n 1" in result.stdout
        assert "--step" not in result.stdout


class TestDoctorCommand:
    """Tests for weld doctor command."""

    def test_doctor_help(self, runner: CliRunner) -> None:
        """doctor --help should show usage."""
        result = runner.invoke(app, ["doctor", "--help"])
        assert result.exit_code == 0

    def test_doctor_shows_tools(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """doctor should show required and optional tools."""
        result = runner.invoke(app, ["doctor"])
        # May pass or fail depending on tools, but should run
        assert "Required Tools" in result.stdout
        assert "Optional Tools" in result.stdout
        assert "git" in result.stdout

    def test_doctor_json_output(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """doctor with --json should output structured JSON with schema version."""
        import json

        from weld.output import SCHEMA_VERSION

        result = runner.invoke(app, ["--json", "doctor"])
        # In JSON mode, output should be valid JSON
        output = result.stdout.strip()

        # Parse the entire output as JSON (now wrapped with schema_version)
        wrapped = json.loads(output)
        assert wrapped["schema_version"] == SCHEMA_VERSION
        data = wrapped["data"]
        assert "success" in data or "error" in data
        assert "required" in data
        assert "optional" in data
        # Verify structure of required tools
        assert "git" in data["required"]
        assert "available" in data["required"]["git"]


class TestNextCommand:
    """Tests for weld next command."""

    def test_next_help(self, runner: CliRunner) -> None:
        """next --help should show usage."""
        result = runner.invoke(app, ["next", "--help"])
        assert result.exit_code == 0

    def test_next_not_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """next should fail when not in a git repository."""
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(app, ["next"])
            assert result.exit_code == 3
            assert "Not a git repository" in result.stdout
        finally:
            os.chdir(original)

    def test_next_no_runs(self, runner: CliRunner, initialized_weld: Path) -> None:
        """next should show message when no runs exist."""
        result = runner.invoke(app, ["next"])
        assert result.exit_code == 0
        # May show either "No runs found" or "No active runs found"
        assert "No" in result.stdout and "runs" in result.stdout

    def test_next_shows_status(self, runner: CliRunner, run_with_plan: tuple[Path, str]) -> None:
        """next should show status of most recent run."""
        _repo_root, run_id = run_with_plan
        result = runner.invoke(app, ["next"])
        assert result.exit_code == 0
        # Should show run info (delegates to status)
        assert run_id in result.stdout


class TestRunSubcommands:
    """Tests for weld run subcommands."""

    def test_run_help(self, runner: CliRunner) -> None:
        """run --help should list subcommands."""
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "start" in result.stdout
        assert "abandon" in result.stdout
        assert "continue" in result.stdout

    def test_run_no_args_shows_help(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """run with no args should show help."""
        result = runner.invoke(app, ["run"])
        assert result.exit_code == 0
        assert "Run management commands" in result.stdout
        assert "start" in result.stdout

    def test_run_abandon_nonexistent(self, runner: CliRunner, initialized_weld: Path) -> None:
        """run abandon should fail for nonexistent run."""
        result = runner.invoke(app, ["run", "abandon", "--run", "nonexistent", "--force"])
        assert result.exit_code == 1
        assert "Run not found" in result.stdout

    def test_run_abandon_marks_as_abandoned(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """run abandon should mark run as abandoned."""
        from weld.models import Meta

        repo_root, run_id = run_with_plan
        result = runner.invoke(app, ["run", "abandon", "--run", run_id, "--force"])
        assert result.exit_code == 0
        assert "abandoned" in result.stdout.lower()

        # Verify meta was updated
        meta_path = repo_root / ".weld" / "runs" / run_id / "meta.json"
        meta = Meta.model_validate_json(meta_path.read_text())
        assert meta.abandoned is True
        assert meta.abandoned_at is not None

    def test_run_abandon_already_abandoned(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """run abandon should handle already abandoned run."""
        _repo_root, run_id = run_with_plan
        # Abandon once
        runner.invoke(app, ["run", "abandon", "--run", run_id, "--force"])
        # Try again
        result = runner.invoke(app, ["run", "abandon", "--run", run_id, "--force"])
        assert result.exit_code == 0
        assert "already abandoned" in result.stdout.lower()

    def test_run_continue_nonexistent(self, runner: CliRunner, initialized_weld: Path) -> None:
        """run continue should fail when no active runs."""
        result = runner.invoke(app, ["run", "continue"])
        assert result.exit_code == 1
        assert "No runs found" in result.stdout or "No active runs" in result.stdout

    def test_run_continue_shows_status(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """run continue should show status of run."""
        _repo_root, run_id = run_with_plan
        result = runner.invoke(app, ["run", "continue", "--run", run_id])
        assert result.exit_code == 0
        assert run_id in result.stdout


class TestStepSkipCommand:
    """Tests for weld step skip command."""

    def test_step_skip_help(self, runner: CliRunner) -> None:
        """step skip --help should show usage."""
        result = runner.invoke(app, ["step", "skip", "--help"])
        assert result.exit_code == 0
        assert "--run" in result.stdout
        assert "--n" in result.stdout
        assert "--reason" in result.stdout

    def test_step_skip_not_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """step skip should fail when not in a git repository."""
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(
                app, ["step", "skip", "--run", "test", "--n", "1", "--reason", "test"]
            )
            assert result.exit_code == 3
            assert "Not a git repository" in result.stdout
        finally:
            os.chdir(original)

    def test_step_skip_nonexistent_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """step skip should fail for nonexistent run."""
        result = runner.invoke(
            app, ["step", "skip", "--run", "nonexistent", "--n", "1", "--reason", "test"]
        )
        assert result.exit_code == 1
        assert "Run not found" in result.stdout

    def test_step_skip_no_steps(self, runner: CliRunner, run_with_plan: tuple[Path, str]) -> None:
        """step skip should fail when no steps directory exists."""
        repo_root, run_id = run_with_plan
        # Ensure steps directory doesn't exist or is empty
        steps_dir = repo_root / ".weld" / "runs" / run_id / "steps"
        if steps_dir.exists():
            import shutil

            shutil.rmtree(steps_dir)

        result = runner.invoke(
            app, ["step", "skip", "--run", run_id, "--n", "1", "--reason", "test"]
        )
        assert result.exit_code == 1
        assert "No steps found" in result.stdout

    def test_step_skip_nonexistent_step(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """step skip should fail for nonexistent step number."""
        repo_root, run_id = run_with_plan
        # Create steps dir with step 1 only
        steps_dir = repo_root / ".weld" / "runs" / run_id / "steps"
        steps_dir.mkdir(exist_ok=True)
        (steps_dir / "01-setup").mkdir()

        result = runner.invoke(
            app, ["step", "skip", "--run", run_id, "--n", "99", "--reason", "test"]
        )
        assert result.exit_code == 1
        assert "Step 99 not found" in result.stdout

    def test_step_skip_marks_as_skipped(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """step skip should create skip marker file."""
        repo_root, run_id = run_with_plan
        steps_dir = repo_root / ".weld" / "runs" / run_id / "steps"
        steps_dir.mkdir(exist_ok=True)
        step_dir = steps_dir / "01-setup"
        step_dir.mkdir()

        result = runner.invoke(
            app, ["step", "skip", "--run", run_id, "--n", "1", "--reason", "Not needed"]
        )
        assert result.exit_code == 0
        assert "skipped" in result.stdout.lower()

        # Verify skip marker was created
        skip_marker = step_dir / "skipped"
        assert skip_marker.exists()
        assert skip_marker.read_text() == "Not needed"

    def test_step_skip_already_skipped(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """step skip should handle already skipped step."""
        repo_root, run_id = run_with_plan
        steps_dir = repo_root / ".weld" / "runs" / run_id / "steps"
        steps_dir.mkdir(exist_ok=True)
        step_dir = steps_dir / "01-setup"
        step_dir.mkdir()
        (step_dir / "skipped").write_text("Previous reason")

        result = runner.invoke(
            app, ["step", "skip", "--run", run_id, "--n", "1", "--reason", "New reason"]
        )
        assert result.exit_code == 0
        assert "already skipped" in result.stdout.lower()

    def test_step_skip_already_completed(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """step skip should handle already completed step."""
        repo_root, run_id = run_with_plan
        steps_dir = repo_root / ".weld" / "runs" / run_id / "steps"
        steps_dir.mkdir(exist_ok=True)
        step_dir = steps_dir / "01-setup"
        step_dir.mkdir()
        (step_dir / "completed").write_text("")

        result = runner.invoke(
            app, ["step", "skip", "--run", run_id, "--n", "1", "--reason", "test"]
        )
        assert result.exit_code == 0
        assert "already completed" in result.stdout.lower()

    def test_step_skip_dry_run(self, runner: CliRunner, run_with_plan: tuple[Path, str]) -> None:
        """step skip --dry-run should not create marker."""
        repo_root, run_id = run_with_plan
        steps_dir = repo_root / ".weld" / "runs" / run_id / "steps"
        steps_dir.mkdir(exist_ok=True)
        step_dir = steps_dir / "01-setup"
        step_dir.mkdir()

        result = runner.invoke(
            app,
            ["--dry-run", "step", "skip", "--run", run_id, "--n", "1", "--reason", "test"],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout

        # Verify no skip marker was created
        assert not (step_dir / "skipped").exists()
