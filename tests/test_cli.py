"""CLI integration tests for weld."""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from weld import __version__
from weld.cli import app


class TestVersionCommand:
    """Tests for --version flag."""

    def test_version_shows_version(self, runner: CliRunner) -> None:
        """--version should display version string."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "weld" in result.stdout
        assert __version__ in result.stdout

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
        assert "plan" in result.stdout
        assert "research" in result.stdout
        assert "discover" in result.stdout
        assert "interview" in result.stdout
        assert "review" in result.stdout
        assert "commit" in result.stdout

    def test_no_args_shows_help(self, runner: CliRunner) -> None:
        """Running with no args should show help."""
        result = runner.invoke(app, [])
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
        """init should succeed when all required tools are present."""

        def mock_subprocess_run(
            cmd: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("weld.commands.init.subprocess.run", side_effect=mock_subprocess_run):
            result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert "initialized successfully" in result.stdout.lower()

    def test_init_dry_run_no_side_effects(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """init --dry-run should not create any directories or files."""
        weld_dir = temp_git_repo / ".weld"
        assert not weld_dir.exists()

        result = runner.invoke(app, ["--dry-run", "init"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert not weld_dir.exists()


class TestPlanCommand:
    """Tests for weld plan command."""

    def test_plan_help(self, runner: CliRunner) -> None:
        """plan --help should show options."""
        result = runner.invoke(app, ["plan", "--help"])
        assert result.exit_code == 0
        assert "--output" in result.stdout

    def test_plan_missing_file(self, runner: CliRunner, initialized_weld: Path) -> None:
        """plan should fail when input file doesn't exist."""
        result = runner.invoke(app, ["plan", "nonexistent.md", "-o", "plan.md"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_plan_dry_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """plan --dry-run should show prompt without calling Claude."""
        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# Test Spec\n\nImplement something.")

        result = runner.invoke(app, ["--dry-run", "plan", str(spec_file), "-o", "plan.md"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "Implementation Plan Request" in result.stdout
        # Verify Phase/Step structure is in output
        assert "## Phase <number>:" in result.stdout
        assert "### Step <number>:" in result.stdout
        assert "**Phase guidelines:**" in result.stdout
        assert "**Step guidelines:**" in result.stdout
        # Verify concrete example is included
        assert "## Example" in result.stdout
        assert "## Phase 1: Data Models" in result.stdout


class TestResearchCommand:
    """Tests for weld research command."""

    def test_research_help(self, runner: CliRunner) -> None:
        """research --help should show options."""
        result = runner.invoke(app, ["research", "--help"])
        assert result.exit_code == 0
        assert "--output" in result.stdout
        assert "--focus" in result.stdout

    def test_research_missing_file(self, runner: CliRunner, initialized_weld: Path) -> None:
        """research should fail when input file doesn't exist."""
        result = runner.invoke(app, ["research", "nonexistent.md", "-o", "research.md"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_research_dry_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """research --dry-run should show prompt without calling Claude."""
        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# Test Spec\n\nImplement something.")

        result = runner.invoke(app, ["--dry-run", "research", str(spec_file), "-o", "research.md"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "Research Request" in result.stdout

    def test_research_focus_in_dry_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """research --focus should include focus areas in prompt."""
        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# Test Spec\n\nImplement something.")

        result = runner.invoke(
            app,
            [
                "--dry-run",
                "research",
                str(spec_file),
                "-o",
                "research.md",
                "--focus",
                "security and auth",
            ],
        )
        assert result.exit_code == 0
        assert "Focus Areas" in result.stdout
        assert "security and auth" in result.stdout


class TestCommitCommand:
    """Tests for weld commit command."""

    def test_commit_not_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """commit should fail when not in a git repository."""
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(app, ["commit"])
            assert result.exit_code == 3
        finally:
            os.chdir(original)

    def test_commit_no_staged_changes(self, runner: CliRunner, initialized_weld: Path) -> None:
        """commit should fail when no staged changes."""
        result = runner.invoke(app, ["commit"])
        assert result.exit_code == 20
        assert "No changes" in result.stdout


class TestDiscoverCommands:
    """Tests for weld discover command."""

    def test_discover_help(self, runner: CliRunner) -> None:
        """discover --help should show options."""
        result = runner.invoke(app, ["discover", "--help"])
        assert result.exit_code == 0
        assert "--output" in result.stdout

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

    def test_discover_dry_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """discover --dry-run should not call Claude."""
        result = runner.invoke(app, ["--dry-run", "discover", "--output", "arch.md"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout


class TestInterviewCommand:
    """Tests for weld interview command."""

    def test_interview_help(self, runner: CliRunner) -> None:
        """interview --help should show usage."""
        result = runner.invoke(app, ["interview", "--help"])
        assert result.exit_code == 0
        assert "file" in result.stdout.lower()

    def test_interview_file_not_found(self, runner: CliRunner, initialized_weld: Path) -> None:
        """interview should fail when file doesn't exist."""
        result = runner.invoke(app, ["interview", "nonexistent.md"])
        assert result.exit_code == 1
        assert "File not found" in result.stdout


class TestReviewCommand:
    """Tests for weld review command."""

    def test_review_help(self, runner: CliRunner) -> None:
        """review --help should show options."""
        result = runner.invoke(app, ["review", "--help"])
        assert result.exit_code == 0
        assert "--diff" in result.stdout
        assert "--staged" in result.stdout
        assert "--apply" in result.stdout

    def test_review_requires_document_or_diff(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """review without args or --diff should fail."""
        result = runner.invoke(app, ["review"])
        assert result.exit_code == 1
        assert "Either provide a document or use --diff" in result.stdout

    def test_review_diff_conflicts_with_document(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """review --diff with document argument should fail."""
        doc = initialized_weld / "doc.md"
        doc.write_text("# Doc")
        result = runner.invoke(app, ["review", "--diff", str(doc)])
        assert result.exit_code == 1
        assert "Cannot use --diff with a document" in result.stdout

    def test_review_staged_requires_diff(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review --staged without --diff should fail."""
        result = runner.invoke(app, ["review", "--staged"])
        assert result.exit_code == 1
        assert "--staged requires --diff" in result.stdout

    def test_review_diff_no_changes(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review --diff with no uncommitted changes should show message."""
        result = runner.invoke(app, ["review", "--diff"])
        assert result.exit_code == 0
        assert "No uncommitted changes" in result.stdout

    def test_review_document_not_found(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review with nonexistent document should fail."""
        result = runner.invoke(app, ["review", "nonexistent.md"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()


class TestDoctorCommand:
    """Tests for weld doctor command."""

    def test_doctor_help(self, runner: CliRunner) -> None:
        """doctor --help should show usage."""
        result = runner.invoke(app, ["doctor", "--help"])
        assert result.exit_code == 0

    def test_doctor_shows_tools(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """doctor should show required and optional tools."""
        result = runner.invoke(app, ["doctor"])
        assert "Required Tools" in result.stdout
        assert "Optional Tools" in result.stdout
        assert "git" in result.stdout


class TestInitCommandDetailed:
    """Detailed tests for init command verifying actual behavior."""

    def test_init_checks_required_tools(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """init should check for all required CLI tools."""
        checked_tools: list[str] = []

        def mock_subprocess_run(
            cmd: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            checked_tools.append(cmd[0])
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("weld.commands.init.subprocess.run", side_effect=mock_subprocess_run):
            runner.invoke(app, ["init"])

        # init checks: git, gh, codex
        assert "git" in checked_tools
        assert "gh" in checked_tools
        assert "codex" in checked_tools

    def test_init_creates_weld_directory(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """init should create .weld directory."""

        def mock_subprocess_run(
            cmd: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("weld.commands.init.subprocess.run", side_effect=mock_subprocess_run):
            result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        weld_dir = temp_git_repo / ".weld"
        assert weld_dir.exists()

    def test_init_creates_config_file(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """init should create config.toml file."""

        def mock_subprocess_run(
            cmd: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("weld.commands.init.subprocess.run", side_effect=mock_subprocess_run):
            runner.invoke(app, ["init"])

        config_file = temp_git_repo / ".weld" / "config.toml"
        assert config_file.exists()

    def test_init_fails_with_missing_codex(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """init should fail when codex is not installed."""

        def mock_subprocess_run(
            cmd: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if cmd[0] == "codex":
                raise FileNotFoundError("codex not found")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("weld.commands.init.subprocess.run", side_effect=mock_subprocess_run):
            result = runner.invoke(app, ["init"])

        assert result.exit_code == 2
        assert "codex" in result.stdout.lower()
        assert "not found" in result.stdout.lower()

    def test_init_creates_gitignore_if_missing(
        self, runner: CliRunner, temp_git_repo: Path
    ) -> None:
        """init should create .gitignore with .weld/ exclusions if it doesn't exist."""

        def mock_subprocess_run(
            cmd: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("weld.commands.init.subprocess.run", side_effect=mock_subprocess_run):
            runner.invoke(app, ["init"])

        gitignore = temp_git_repo / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        assert ".weld/*" in content
        assert "!.weld/config.toml" in content

    def test_init_updates_existing_gitignore(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """init should update existing .gitignore with .weld/ exclusions."""
        gitignore = temp_git_repo / ".gitignore"
        gitignore.write_text("node_modules/\n*.log\n")

        def mock_subprocess_run(
            cmd: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("weld.commands.init.subprocess.run", side_effect=mock_subprocess_run):
            runner.invoke(app, ["init"])

        content = gitignore.read_text()
        assert "node_modules/" in content
        assert "*.log" in content
        assert ".weld/*" in content
        assert "!.weld/config.toml" in content

    def test_init_skips_duplicate_gitignore_entries(
        self, runner: CliRunner, temp_git_repo: Path
    ) -> None:
        """init should not duplicate .weld/ entries if they already exist."""
        gitignore = temp_git_repo / ".gitignore"
        gitignore.write_text(".weld/*\n!.weld/config.toml\n")

        def mock_subprocess_run(
            cmd: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch("weld.commands.init.subprocess.run", side_effect=mock_subprocess_run):
            result = runner.invoke(app, ["init"])

        content = gitignore.read_text()
        # Count occurrences - should appear only once
        assert content.count(".weld/*") == 1
        assert content.count("!.weld/config.toml") == 1
        assert "already excludes .weld/" in result.stdout


class TestPlanCommandDetailed:
    """Detailed tests for plan command verifying actual behavior."""

    def test_plan_success_creates_output_file(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """plan should create output file on success."""
        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# Test Spec\n\nDo something.")
        output_file = initialized_weld / "plan.md"

        plan_output = "# Implementation Plan\n\n## Step 1"
        with patch("weld.commands.plan.run_claude", return_value=plan_output):
            result = runner.invoke(app, ["plan", str(spec_file), "-o", str(output_file)])

        assert result.exit_code == 0
        assert output_file.exists()
        assert "Implementation Plan" in output_file.read_text()

    def test_plan_passes_prompt_to_claude(self, runner: CliRunner, initialized_weld: Path) -> None:
        """plan should pass spec content in prompt to Claude."""
        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# My Feature\n\nBuild a widget parser.")
        output_file = initialized_weld / "plan.md"

        captured_prompt = []

        def capture_claude(prompt: str, **kwargs: object) -> str:
            captured_prompt.append(prompt)
            return "Plan output"

        with patch("weld.commands.plan.run_claude", side_effect=capture_claude):
            runner.invoke(app, ["plan", str(spec_file), "-o", str(output_file)])

        assert len(captured_prompt) == 1
        assert "My Feature" in captured_prompt[0]
        assert "widget parser" in captured_prompt[0]

    def test_plan_handles_claude_error(self, runner: CliRunner, initialized_weld: Path) -> None:
        """plan should handle ClaudeError gracefully."""
        from weld.services import ClaudeError

        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# Spec\n\nContent")

        with patch("weld.commands.plan.run_claude", side_effect=ClaudeError("API error")):
            result = runner.invoke(app, ["plan", str(spec_file), "-o", "plan.md"])

        assert result.exit_code == 1
        assert "Claude failed" in result.stdout

    def test_plan_creates_parent_directories(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """plan should create parent directories for output."""
        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# Spec")
        output_file = initialized_weld / "output" / "nested" / "plan.md"

        with patch("weld.commands.plan.run_claude", return_value="Plan"):
            result = runner.invoke(app, ["plan", str(spec_file), "-o", str(output_file)])

        assert result.exit_code == 0
        assert output_file.exists()


class TestResearchCommandDetailed:
    """Detailed tests for research command verifying actual behavior."""

    def test_research_success_creates_output_file(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """research should create output file on success."""
        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# Test Spec\n\nAnalyze this.")
        output_file = initialized_weld / "research.md"

        with patch("weld.commands.research.run_claude", return_value="# Research Findings\n"):
            result = runner.invoke(app, ["research", str(spec_file), "-o", str(output_file)])

        assert result.exit_code == 0
        assert output_file.exists()
        assert "Research Findings" in output_file.read_text()

    def test_research_passes_spec_to_claude(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """research should pass spec content to Claude."""
        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# Auth System\n\nImplement OAuth2 flow.")
        output_file = initialized_weld / "research.md"

        captured_prompt = []

        def capture_claude(prompt: str, **kwargs: object) -> str:
            captured_prompt.append(prompt)
            return "Research output"

        with patch("weld.commands.research.run_claude", side_effect=capture_claude):
            runner.invoke(app, ["research", str(spec_file), "-o", str(output_file)])

        assert len(captured_prompt) == 1
        assert "Auth System" in captured_prompt[0]
        assert "OAuth2" in captured_prompt[0]

    def test_research_handles_claude_error(self, runner: CliRunner, initialized_weld: Path) -> None:
        """research should handle ClaudeError gracefully."""
        from weld.services import ClaudeError

        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# Spec")

        with patch("weld.commands.research.run_claude", side_effect=ClaudeError("Timeout")):
            result = runner.invoke(app, ["research", str(spec_file), "-o", "research.md"])

        assert result.exit_code == 1
        assert "Claude failed" in result.stdout


class TestDiscoverCommandDetailed:
    """Detailed tests for discover command verifying actual behavior."""

    def test_discover_success_creates_output_file(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """discover should create output file on success."""
        output_file = initialized_weld / "architecture.md"

        with patch("weld.commands.discover.run_claude", return_value="# Architecture\n\nOverview"):
            result = runner.invoke(app, ["discover", "-o", str(output_file)])

        assert result.exit_code == 0
        assert output_file.exists()
        assert "Architecture" in output_file.read_text()

    def test_discover_strips_preamble(self, runner: CliRunner, initialized_weld: Path) -> None:
        """discover should strip AI preamble from output."""
        output_file = initialized_weld / "architecture.md"
        claude_output = "I'll analyze this codebase for you.\n\n# Architecture\n\nContent"

        with patch("weld.commands.discover.run_claude", return_value=claude_output):
            result = runner.invoke(app, ["discover", "-o", str(output_file)])

        assert result.exit_code == 0
        content = output_file.read_text()
        assert "I'll analyze" not in content
        assert content.startswith("# Architecture")

    def test_discover_with_focus(self, runner: CliRunner, initialized_weld: Path) -> None:
        """discover should include focus area in prompt."""
        output_file = initialized_weld / "architecture.md"
        captured_prompt = []

        def capture_claude(prompt: str, **kwargs: object) -> str:
            captured_prompt.append(prompt)
            return "# Architecture"

        with patch("weld.commands.discover.run_claude", side_effect=capture_claude):
            runner.invoke(
                app, ["discover", "-o", str(output_file), "--focus", "API layer security"]
            )

        assert len(captured_prompt) == 1
        assert "API layer security" in captured_prompt[0]

    def test_discover_handles_claude_error(self, runner: CliRunner, initialized_weld: Path) -> None:
        """discover should handle ClaudeError gracefully."""
        from weld.services import ClaudeError

        with patch("weld.commands.discover.run_claude", side_effect=ClaudeError("Rate limited")):
            result = runner.invoke(app, ["discover", "-o", "arch.md"])

        assert result.exit_code == 1
        assert "Claude failed" in result.stdout

    def test_discover_prompt_only(self, runner: CliRunner, initialized_weld: Path) -> None:
        """discover --prompt-only should output prompt without calling Claude."""
        with patch("weld.commands.discover.run_claude") as mock_claude:
            result = runner.invoke(app, ["discover", "-o", "arch.md", "--prompt-only"])

        assert result.exit_code == 0
        mock_claude.assert_not_called()
        assert "System Architecture" in result.stdout


class TestCommitCommandDetailed:
    """Detailed tests for commit command verifying actual behavior."""

    def _mock_claude_response(self, files: list[str] | None = None) -> str:
        """Return a mock Claude response with commit groups in new format."""
        file_list = "\n".join(files) if files else "test.txt"
        return f"""<commit>
<files>
{file_list}
</files>
<commit_message>
Add test file

This is a test commit message.
</commit_message>
<changelog_entry>
### Added
- Test file for unit testing
</changelog_entry>
</commit>"""

    def test_commit_requires_weld_init(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """commit should fail if weld is not initialized."""
        # Create a file and stage it
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=temp_git_repo, check=True)

        result = runner.invoke(app, ["commit"])

        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    def test_commit_success_with_staged_changes(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """commit should succeed when there are staged changes."""
        # Create and stage a file
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        # Mock Claude and skip transcript (no session detected)
        with (
            patch("weld.commands.commit.run_claude", return_value=self._mock_claude_response()),
            patch("weld.commands.commit.detect_current_session", return_value=None),
        ):
            result = runner.invoke(app, ["commit"])

        assert result.exit_code == 0
        assert "Committed:" in result.stdout

    def test_commit_with_skip_transcript(self, runner: CliRunner, initialized_weld: Path) -> None:
        """commit --skip-transcript should not upload transcript."""
        # Create and stage a file
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        with (
            patch("weld.commands.commit.run_claude", return_value=self._mock_claude_response()),
            patch("weld.commands.commit.upload_gist") as mock_upload,
        ):
            result = runner.invoke(app, ["commit", "--skip-transcript"])

        assert result.exit_code == 0
        mock_upload.assert_not_called()

    def test_commit_stages_all_with_flag(self, runner: CliRunner, initialized_weld: Path) -> None:
        """commit --all should stage all changes before committing."""
        # Create unstaged file
        test_file = initialized_weld / "unstaged.txt"
        test_file.write_text("content")

        with patch(
            "weld.commands.commit.run_claude",
            return_value=self._mock_claude_response(files=["unstaged.txt"]),
        ):
            result = runner.invoke(
                app, ["commit", "--all", "--skip-transcript", "--skip-changelog"]
            )

        assert result.exit_code == 0
        assert "Committed:" in result.stdout

    def test_commit_handles_git_error(self, runner: CliRunner, initialized_weld: Path) -> None:
        """commit should handle GitError from commit_file."""
        from weld.services import GitError

        # Create and stage a file
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        commit_error = GitError("Pre-commit hook failed")
        with (
            patch("weld.commands.commit.run_claude", return_value=self._mock_claude_response()),
            patch("weld.commands.commit.detect_current_session", return_value=None),
            patch("weld.commands.commit.commit_file", side_effect=commit_error),
        ):
            result = runner.invoke(app, ["commit"])

        assert result.exit_code == 22
        assert "Commit failed" in result.stdout

    def test_commit_transcript_failure_is_warning(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """commit should continue with warning when transcript upload fails."""
        from weld.services.gist_uploader import GistError

        # Create and stage a file
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        # Create a fake session file
        fake_session = initialized_weld / ".claude-session.jsonl"
        fake_session.write_text("{}\n")

        with (
            patch("weld.commands.commit.run_claude", return_value=self._mock_claude_response()),
            patch("weld.commands.commit.detect_current_session", return_value=fake_session),
            patch("weld.commands.commit.get_session_id", return_value="abc123"),
            patch("weld.commands.commit.render_transcript", return_value="# Transcript"),
            patch("weld.commands.commit.upload_gist", side_effect=GistError("Network error")),
        ):
            result = runner.invoke(app, ["commit"])

        assert result.exit_code == 0
        assert "skipped" in result.stdout.lower()
        assert "Committed:" in result.stdout

    def test_commit_skip_changelog_flag(self, runner: CliRunner, initialized_weld: Path) -> None:
        """commit --skip-changelog should not update CHANGELOG.md."""
        # Create CHANGELOG.md
        changelog = initialized_weld / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [Unreleased]\n\n## [1.0.0]\n- Initial release\n")

        # Create and stage a file
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        original_changelog = changelog.read_text()

        with patch("weld.commands.commit.run_claude", return_value=self._mock_claude_response()):
            result = runner.invoke(app, ["commit", "--skip-transcript", "--skip-changelog"])

        assert result.exit_code == 0
        # CHANGELOG should be unchanged
        assert changelog.read_text() == original_changelog

    def test_commit_quiet_flag(self, runner: CliRunner, initialized_weld: Path) -> None:
        """commit --quiet should suppress streaming output."""
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        with patch(
            "weld.commands.commit.run_claude", return_value=self._mock_claude_response()
        ) as mock:
            result = runner.invoke(
                app, ["commit", "--skip-transcript", "--skip-changelog", "--quiet"]
            )

        assert result.exit_code == 0
        # Verify run_claude was called with stream=False
        mock.assert_called_once()
        call_kwargs = mock.call_args[1]
        assert call_kwargs.get("stream") is False

    def test_commit_message_in_git_log(self, runner: CliRunner, initialized_weld: Path) -> None:
        """commit should use the generated commit message in git log."""
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        with patch("weld.commands.commit.run_claude", return_value=self._mock_claude_response()):
            result = runner.invoke(app, ["commit", "--skip-transcript", "--skip-changelog"])

        assert result.exit_code == 0

        # Verify the commit message is in git log
        log_result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=initialized_weld,
            capture_output=True,
            text=True,
        )
        assert log_result.stdout.strip() == "Add test file"

    def test_commit_claude_error(self, runner: CliRunner, initialized_weld: Path) -> None:
        """commit should fail with exit code 21 when Claude fails."""
        from weld.services.claude import ClaudeError

        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        with patch(
            "weld.commands.commit.run_claude",
            side_effect=ClaudeError("Claude CLI not found"),
        ):
            result = runner.invoke(app, ["commit", "--skip-transcript"])

        assert result.exit_code == 21
        assert "Failed to generate commit message" in result.stdout

    def test_commit_parse_failure(self, runner: CliRunner, initialized_weld: Path) -> None:
        """commit should fail with exit code 23 when Claude response doesn't parse."""
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        # Return garbage that doesn't contain the expected XML tags
        with patch("weld.commands.commit.run_claude", return_value="This is not valid XML output"):
            result = runner.invoke(app, ["commit", "--skip-transcript"])

        assert result.exit_code == 23
        assert "Could not parse commit groups" in result.stdout
        # Should show Claude's response for debugging
        assert "This is not valid XML output" in result.stdout

    def test_commit_changelog_no_unreleased_section(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """commit should handle CHANGELOG.md without [Unreleased] section."""
        # Create CHANGELOG without [Unreleased]
        changelog = initialized_weld / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [1.0.0]\n- Initial release\n")

        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        original_changelog = changelog.read_text()

        with patch("weld.commands.commit.run_claude", return_value=self._mock_claude_response()):
            result = runner.invoke(app, ["commit", "--skip-transcript"])

        assert result.exit_code == 0
        # CHANGELOG should be unchanged (couldn't update)
        assert changelog.read_text() == original_changelog
        assert "Could not update CHANGELOG.md" in result.stdout

    def test_commit_changelog_no_file(self, runner: CliRunner, initialized_weld: Path) -> None:
        """commit should handle missing CHANGELOG.md gracefully."""
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        # Ensure no CHANGELOG exists
        changelog = initialized_weld / "CHANGELOG.md"
        if changelog.exists():
            changelog.unlink()

        with patch("weld.commands.commit.run_claude", return_value=self._mock_claude_response()):
            result = runner.invoke(app, ["commit", "--skip-transcript"])

        assert result.exit_code == 0
        assert "Committed:" in result.stdout
        # Should show warning about changelog
        assert "Could not update CHANGELOG.md" in result.stdout

    def test_commit_changelog_duplicate_detection(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """commit should not add duplicate entries to CHANGELOG."""
        # Create CHANGELOG with existing entry
        changelog = initialized_weld / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [Unreleased]\n\n### Added\n- Test file for unit testing\n\n"
        )

        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        original_changelog = changelog.read_text()

        with patch("weld.commands.commit.run_claude", return_value=self._mock_claude_response()):
            result = runner.invoke(app, ["commit", "--skip-transcript"])

        assert result.exit_code == 0
        # CHANGELOG should be unchanged (duplicate detected)
        assert changelog.read_text() == original_changelog

    def test_commit_changelog_updates_correctly(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """commit should correctly update CHANGELOG.md with new entry."""
        # Create CHANGELOG
        changelog = initialized_weld / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [Unreleased]\n\n## [1.0.0]\n- Initial release\n")

        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        with patch("weld.commands.commit.run_claude", return_value=self._mock_claude_response()):
            result = runner.invoke(app, ["commit", "--skip-transcript"])

        assert result.exit_code == 0
        assert "Updated CHANGELOG.md" in result.stdout

        # Verify the changelog was updated
        updated_changelog = changelog.read_text()
        assert "### Added" in updated_changelog
        assert "- Test file for unit testing" in updated_changelog


class TestDefaultOutputPaths:
    """Tests for default output path behavior when --output is omitted."""

    def test_plan_default_output_in_weld_dir(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """plan without --output should write to .weld/plan/."""
        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# Test Spec")

        with patch("weld.commands.plan.run_claude", return_value="# Plan"):
            result = runner.invoke(app, ["plan", str(spec_file)])

        assert result.exit_code == 0
        plan_dir = initialized_weld / ".weld" / "plan"
        assert plan_dir.exists()
        plan_files = list(plan_dir.glob("spec-*.md"))
        assert len(plan_files) == 1
        assert plan_files[0].read_text() == "# Plan"

    def test_plan_without_weld_init_fails(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """plan without --output should fail if weld not initialized."""
        spec_file = temp_git_repo / "spec.md"
        spec_file.write_text("# Test Spec")

        result = runner.invoke(app, ["plan", str(spec_file)])

        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    def test_research_default_output_in_weld_dir(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """research without --output should write to .weld/research/."""
        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# Test Spec")

        with patch("weld.commands.research.run_claude", return_value="# Research"):
            result = runner.invoke(app, ["research", str(spec_file)])

        assert result.exit_code == 0
        research_dir = initialized_weld / ".weld" / "research"
        assert research_dir.exists()
        research_files = list(research_dir.glob("spec-*.md"))
        assert len(research_files) == 1
        assert research_files[0].read_text() == "# Research"

    def test_research_without_weld_init_fails(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """research without --output should fail if weld not initialized."""
        spec_file = temp_git_repo / "spec.md"
        spec_file.write_text("# Test Spec")

        result = runner.invoke(app, ["research", str(spec_file)])

        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    def test_discover_default_output_in_weld_dir(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """discover without --output should write to .weld/discover/."""
        with patch("weld.commands.discover.run_claude", return_value="# Architecture"):
            result = runner.invoke(app, ["discover"])

        assert result.exit_code == 0
        discover_dir = initialized_weld / ".weld" / "discover"
        assert discover_dir.exists()
        discover_files = list(discover_dir.glob("*.md"))
        assert len(discover_files) == 1
        assert discover_files[0].read_text() == "# Architecture"

    def test_discover_without_weld_init_fails(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """discover without --output should fail if weld not initialized."""
        result = runner.invoke(app, ["discover"])

        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    def test_plan_with_explicit_output_works_without_init(
        self, runner: CliRunner, temp_git_repo: Path
    ) -> None:
        """plan with --output should work without weld init."""
        spec_file = temp_git_repo / "spec.md"
        spec_file.write_text("# Test Spec")
        output_file = temp_git_repo / "plan.md"

        with patch("weld.commands.plan.run_claude", return_value="# Plan"):
            result = runner.invoke(app, ["plan", str(spec_file), "-o", str(output_file)])

        assert result.exit_code == 0
        assert output_file.exists()
        assert output_file.read_text() == "# Plan"

    def test_research_with_explicit_output_works_without_init(
        self, runner: CliRunner, temp_git_repo: Path
    ) -> None:
        """research with --output should work without weld init."""
        spec_file = temp_git_repo / "spec.md"
        spec_file.write_text("# Test Spec")
        output_file = temp_git_repo / "research.md"

        with patch("weld.commands.research.run_claude", return_value="# Research"):
            result = runner.invoke(app, ["research", str(spec_file), "-o", str(output_file)])

        assert result.exit_code == 0
        assert output_file.exists()
        assert output_file.read_text() == "# Research"

    def test_discover_with_explicit_output_works_without_init(
        self, runner: CliRunner, temp_git_repo: Path
    ) -> None:
        """discover with --output should work without weld init."""
        output_file = temp_git_repo / "architecture.md"

        with patch("weld.commands.discover.run_claude", return_value="# Architecture"):
            result = runner.invoke(app, ["discover", "-o", str(output_file)])

        assert result.exit_code == 0
        assert output_file.exists()
        assert output_file.read_text() == "# Architecture"
