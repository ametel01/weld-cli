"""Tests for implement command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from weld.cli import app

runner = CliRunner(
    env={
        "NO_COLOR": "1",
        "TERM": "dumb",
        "COLUMNS": "200",
    },
)


class TestImplementCommand:
    """Test implement CLI command."""

    @pytest.mark.cli
    def test_implement_help(self) -> None:
        """Shows help text with all options."""
        result = runner.invoke(app, ["implement", "--help"])
        assert result.exit_code == 0
        assert "plan_file" in result.output.lower()
        assert "--step" in result.output
        assert "--phase" in result.output
        assert "--quiet" in result.output
        assert "--timeout" in result.output

    @pytest.mark.cli
    def test_implement_file_not_found(self, initialized_weld: Path) -> None:
        """Fails with exit code 23 when plan file doesn't exist."""
        result = runner.invoke(app, ["implement", "nonexistent.md", "--step", "1.1"])
        assert result.exit_code == 23
        assert "not found" in result.output.lower()

    @pytest.mark.cli
    @patch("weld.commands.implement.sys")
    def test_implement_dry_run_interactive(
        self,
        mock_sys: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Dry run shows interactive mode."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Do something

Content here.
""")
        # Mock TTY check - interactive mode requires TTY
        mock_sys.stdin.isatty.return_value = True

        result = runner.invoke(app, ["--dry-run", "implement", str(plan_file)])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "Interactive menu" in result.output

    @pytest.mark.cli
    def test_implement_dry_run_step(self, initialized_weld: Path) -> None:
        """Dry run shows non-interactive step mode."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Do something
""")
        result = runner.invoke(app, ["--dry-run", "implement", str(plan_file), "--step", "1.1"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "step 1.1" in result.output.lower()

    @pytest.mark.cli
    def test_implement_empty_plan(self, initialized_weld: Path) -> None:
        """Fails with exit code 23 when plan has no phases."""
        plan_file = initialized_weld / "empty-plan.md"
        plan_file.write_text("# Empty Plan\n\nNo phases here.\n")

        result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])
        assert result.exit_code == 23
        assert "no phases" in result.output.lower()

    @pytest.mark.cli
    def test_implement_step_not_found(self, initialized_weld: Path) -> None:
        """Fails when specified step doesn't exist."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step
""")
        result = runner.invoke(app, ["implement", str(plan_file), "--step", "9.9"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    @pytest.mark.cli
    def test_implement_phase_not_found(self, initialized_weld: Path) -> None:
        """Fails when specified phase doesn't exist."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step
""")
        result = runner.invoke(app, ["implement", str(plan_file), "--phase", "99"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    @pytest.mark.cli
    @patch("weld.commands.implement.run_claude")
    def test_implement_non_interactive_step(
        self,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Non-interactive step mode marks step complete."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step

Do this first.
""")
        mock_claude.return_value = "Done."

        result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

        assert result.exit_code == 0
        updated = plan_file.read_text()
        assert "### Step 1.1: First step **COMPLETE**" in updated

    @pytest.mark.cli
    @patch("weld.commands.implement.run_claude")
    def test_implement_step_already_complete(
        self,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Already complete step returns success without running Claude."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step **COMPLETE**
""")

        result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

        assert result.exit_code == 0
        assert "already complete" in result.output.lower()
        mock_claude.assert_not_called()

    @pytest.mark.cli
    @patch("weld.commands.implement.run_claude")
    def test_implement_phase_sequential(
        self,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Phase mode executes steps sequentially, marking each complete."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First

Do first.

### Step 1.2: Second

Do second.
""")
        mock_claude.return_value = "Done."

        result = runner.invoke(app, ["implement", str(plan_file), "--phase", "1"])

        assert result.exit_code == 0
        # Claude called twice (once per step)
        assert mock_claude.call_count == 2
        # Both steps marked complete
        updated = plan_file.read_text()
        assert "### Step 1.1: First **COMPLETE**" in updated
        assert "### Step 1.2: Second **COMPLETE**" in updated
        # Phase also marked complete
        assert "## Phase 1: Test **COMPLETE**" in updated

    @pytest.mark.cli
    @patch("weld.commands.implement.run_claude")
    def test_implement_phase_stops_on_failure(
        self,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Phase mode stops on first Claude failure."""
        from weld.services import ClaudeError

        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First

### Step 1.2: Second
""")
        # First call succeeds, second fails
        mock_claude.side_effect = [None, ClaudeError("API error")]

        result = runner.invoke(app, ["implement", str(plan_file), "--phase", "1"])

        assert result.exit_code == 21  # Claude failure
        updated = plan_file.read_text()
        # First step marked complete
        assert "### Step 1.1: First **COMPLETE**" in updated
        # Second step NOT marked complete
        assert "### Step 1.2: Second **COMPLETE**" not in updated
        # Phase NOT marked complete
        assert "## Phase 1: Test **COMPLETE**" not in updated

    @pytest.mark.cli
    @patch("weld.commands.implement.sys")
    @patch("weld.commands.implement.TerminalMenu")
    @patch("weld.commands.implement.run_claude")
    def test_implement_interactive_marks_complete(
        self,
        mock_claude: MagicMock,
        mock_menu: MagicMock,
        mock_sys: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Interactive mode marks step complete after successful implementation."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step

Do this first.
""")
        # Mock sys.stdin.isatty to return True for interactive mode check
        mock_sys.stdin.isatty.return_value = True

        # Mock menu: select step 1.1 (index 1, since phase header is index 0)
        # After step completes, loop's all-complete check exits automatically
        mock_menu_instance = MagicMock()
        mock_menu_instance.show.return_value = 1  # Select Step 1.1
        mock_menu.return_value = mock_menu_instance

        mock_claude.return_value = "Done."

        result = runner.invoke(app, ["implement", str(plan_file)])

        assert result.exit_code == 0
        updated = plan_file.read_text()
        assert "### Step 1.1: First step **COMPLETE**" in updated

    @pytest.mark.cli
    def test_implement_json_mode_requires_step_or_phase(self, initialized_weld: Path) -> None:
        """JSON mode without --step or --phase fails."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step
""")

        result = runner.invoke(app, ["--json", "implement", str(plan_file)])

        assert result.exit_code == 1
        assert "not supported with --json" in result.output.lower()

    @pytest.mark.cli
    @patch("weld.commands.implement.run_claude")
    def test_implement_phase_skips_complete_steps(
        self,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Phase mode skips already-complete steps."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First **COMPLETE**

### Step 1.2: Second

Do second.
""")
        mock_claude.return_value = "Done."

        result = runner.invoke(app, ["implement", str(plan_file), "--phase", "1"])

        assert result.exit_code == 0
        # Claude only called once (for step 1.2)
        assert mock_claude.call_count == 1
        updated = plan_file.read_text()
        assert "### Step 1.2: Second **COMPLETE**" in updated
        assert "## Phase 1: Test **COMPLETE**" in updated

    @pytest.mark.cli
    @patch("weld.commands.implement.run_claude")
    def test_implement_phase_all_complete(
        self,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Phase mode with all steps complete does nothing."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First **COMPLETE**

### Step 1.2: Second **COMPLETE**
""")

        result = runner.invoke(app, ["implement", str(plan_file), "--phase", "1"])

        assert result.exit_code == 0
        assert "already complete" in result.output.lower()
        mock_claude.assert_not_called()

    @pytest.mark.cli
    def test_implement_not_initialized(self, temp_git_repo: Path) -> None:
        """Fails when weld not initialized."""
        plan_file = temp_git_repo / "plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First
""")

        result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

        assert result.exit_code == 1
        assert "not initialized" in result.output.lower()

    @pytest.mark.cli
    @patch("weld.commands.implement.mark_step_complete")
    @patch("weld.commands.implement.run_claude")
    def test_implement_step_handles_valueerror(
        self,
        mock_claude: MagicMock,
        mock_mark_step: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Handles ValueError from mark_step_complete gracefully."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step

Do this.
""")
        mock_claude.return_value = "Done."
        # Simulate plan file modified externally between parse and mark_complete
        mock_mark_step.side_effect = ValueError("Line does not match expected header")

        result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

        # Should return failure exit code, not crash
        assert result.exit_code == 21
        assert "failed to mark step complete" in result.output.lower()

    @pytest.mark.cli
    @patch("weld.commands.implement.mark_phase_complete")
    @patch("weld.commands.implement.mark_step_complete")
    @patch("weld.commands.implement.run_claude")
    def test_implement_phase_handles_valueerror(
        self,
        mock_claude: MagicMock,
        mock_mark_step: MagicMock,
        mock_mark_phase: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Handles ValueError from mark_phase_complete gracefully."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Only step

Do this.
""")
        mock_claude.return_value = "Done."
        # Step succeeds, but phase marking fails
        mock_mark_step.return_value = None
        mock_mark_phase.side_effect = ValueError("Phase header modified")

        result = runner.invoke(app, ["implement", str(plan_file), "--phase", "1"])

        # Should return failure exit code, not crash
        assert result.exit_code == 21
        assert "failed to mark phase complete" in result.output.lower()
