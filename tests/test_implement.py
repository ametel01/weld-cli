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

    @pytest.mark.cli
    @patch("weld.commands.implement.Confirm")
    @patch("weld.commands.implement.run_claude")
    def test_implement_error_recovery_with_changes_accepted(
        self,
        mock_claude: MagicMock,
        mock_confirm: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """When Claude fails but files changed, prompts user and marks complete if accepted."""
        from weld.services import ClaudeError

        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Do something

Content here.
""")

        # Mock Claude to create a file then fail
        def create_file_then_fail(*args, **kwargs):
            test_file = initialized_weld / "new_file.py"
            test_file.write_text("# New file\n")
            raise ClaudeError("Claude crashed internally")

        mock_claude.side_effect = create_file_then_fail
        # User confirms to mark complete, but declines review prompts
        mock_confirm.ask.side_effect = [True, False, False]  # complete=yes, review=no

        result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

        # Should succeed because user confirmed
        assert result.exit_code == 0
        # Should show warning about changes and prompt
        assert "files were modified" in result.output.lower()
        # Verify Confirm.ask was called with correct prompts
        assert mock_confirm.ask.call_count >= 1
        first_call_args = mock_confirm.ask.call_args_list[0][0][0]
        assert "work appears complete" in first_call_args.lower()
        # Step should be marked complete
        updated = plan_file.read_text()
        assert "### Step 1.1: Do something **COMPLETE**" in updated

    @pytest.mark.cli
    @patch("weld.commands.implement.Confirm")
    @patch("weld.commands.implement.run_claude")
    def test_implement_error_recovery_with_changes_declined(
        self,
        mock_claude: MagicMock,
        mock_confirm: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """When Claude fails but files changed, prompts user; doesn't mark complete if declined."""
        from weld.services import ClaudeError

        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Do something

Content here.
""")

        # Mock Claude to create a file then fail
        def create_file_then_fail(*args, **kwargs):
            test_file = initialized_weld / "new_file.py"
            test_file.write_text("# New file\n")
            raise ClaudeError("Claude crashed internally")

        mock_claude.side_effect = create_file_then_fail
        # User declines to mark complete
        mock_confirm.ask.return_value = False

        result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

        # Should fail because user declined
        assert result.exit_code == 21
        # Should prompt about changes
        assert "files were modified" in result.output.lower()
        # Step should NOT be marked complete
        updated = plan_file.read_text()
        assert "### Step 1.1: Do something **COMPLETE**" not in updated

    @pytest.mark.cli
    @patch("weld.commands.implement.Confirm")
    @patch("weld.commands.implement.run_claude")
    def test_implement_error_recovery_no_changes(
        self,
        mock_claude: MagicMock,
        mock_confirm: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """When Claude fails with no file changes, doesn't prompt and returns error."""
        from weld.services import ClaudeError

        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Do something

Content here.
""")

        # Mock Claude to fail without creating files
        mock_claude.side_effect = ClaudeError("Connection timeout")

        result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

        # Should fail
        assert result.exit_code == 21
        assert "claude failed" in result.output.lower()
        # Should NOT prompt user (no changes detected)
        assert "work appears complete" not in result.output.lower()
        mock_confirm.ask.assert_not_called()
        # Step should NOT be marked complete
        updated = plan_file.read_text()
        assert "### Step 1.1: Do something **COMPLETE**" not in updated


class TestFindFirstIncompleteIndex:
    """Test _find_first_incomplete_index helper function."""

    @pytest.mark.unit
    def test_finds_first_incomplete_step(self) -> None:
        """Should find first incomplete step, not phase header."""
        from weld.commands.implement import _find_first_incomplete_index
        from weld.core.plan_parser import Phase, Step

        # Phase with first step complete, second incomplete
        phase = Phase(
            number=1,
            title="Test Phase",
            content="",
            line_number=0,
            is_complete=False,  # Phase not complete yet
        )
        step1 = Step(
            number="1.1",
            title="First Step",
            content="",
            line_number=1,
            is_complete=True,  # Complete
        )
        step2 = Step(
            number="1.2",
            title="Second Step",
            content="",
            line_number=3,
            is_complete=False,  # Incomplete
        )
        phase.steps = [step1, step2]

        items = [
            (phase, None),  # Index 0: Phase header (incomplete)
            (phase, step1),  # Index 1: Step 1.1 (complete)
            (phase, step2),  # Index 2: Step 1.2 (incomplete)
        ]

        # Should return index 2 (first incomplete step), not 0 (incomplete phase header)
        assert _find_first_incomplete_index(items) == 2

    @pytest.mark.unit
    def test_finds_incomplete_phase_without_steps(self) -> None:
        """Should find phase header if it has no steps and is incomplete."""
        from weld.commands.implement import _find_first_incomplete_index
        from weld.core.plan_parser import Phase, Step

        # Standalone phase with no steps
        phase = Phase(
            number=1,
            title="Standalone Phase",
            content="Do something",
            line_number=0,
            is_complete=False,
            steps=[],  # No steps
        )

        items: list[tuple[Phase, Step | None]] = [(phase, None)]

        # Should return index 0 (standalone phase)
        assert _find_first_incomplete_index(items) == 0

    @pytest.mark.unit
    def test_returns_zero_when_all_complete(self) -> None:
        """Should return 0 when all items are complete."""
        from weld.commands.implement import _find_first_incomplete_index
        from weld.core.plan_parser import Phase, Step

        phase = Phase(
            number=1,
            title="Complete Phase",
            content="",
            line_number=0,
            is_complete=True,
        )
        step = Step(
            number="1.1",
            title="Complete Step",
            content="",
            line_number=1,
            is_complete=True,
        )
        phase.steps = [step]

        items = [
            (phase, None),
            (phase, step),
        ]

        # Should return 0 (fallback) when everything is complete
        assert _find_first_incomplete_index(items) == 0

    @pytest.mark.unit
    def test_skips_multiple_completed_items(self) -> None:
        """Should skip multiple completed items to find first incomplete."""
        from weld.commands.implement import _find_first_incomplete_index
        from weld.core.plan_parser import Phase, Step

        phase1 = Phase(number=1, title="Phase 1", content="", line_number=0, is_complete=True)
        step1_1 = Step(number="1.1", title="Step 1.1", content="", line_number=1, is_complete=True)
        step1_2 = Step(number="1.2", title="Step 1.2", content="", line_number=2, is_complete=True)
        phase1.steps = [step1_1, step1_2]

        phase2 = Phase(number=2, title="Phase 2", content="", line_number=4, is_complete=False)
        step2_1 = Step(number="2.1", title="Step 2.1", content="", line_number=5, is_complete=False)
        phase2.steps = [step2_1]

        items = [
            (phase1, None),  # Index 0: Complete
            (phase1, step1_1),  # Index 1: Complete
            (phase1, step1_2),  # Index 2: Complete
            (phase2, None),  # Index 3: Incomplete phase header
            (phase2, step2_1),  # Index 4: Incomplete step
        ]

        # Should return index 4 (first incomplete step), not 3 (phase header)
        assert _find_first_incomplete_index(items) == 4


class TestImplementSessionTracking:
    """Test implement session tracking behavior."""

    @pytest.mark.cli
    @patch("weld.commands.implement.run_claude")
    def test_implement_creates_registry_entry(
        self,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Implement should automatically create session registry entry."""
        from weld.services.session_detector import encode_project_path
        from weld.services.session_tracker import SessionRegistry

        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Do something

Content here.
""")

        # Setup: Create fake Claude session
        claude_dir = Path.home() / ".claude" / "projects" / encode_project_path(initialized_weld)
        claude_dir.mkdir(parents=True, exist_ok=True)
        session_file = claude_dir / "test-session-abc123.jsonl"
        session_file.write_text('{"type":"user","message":{"role":"user","content":"test"}}\n')

        mock_claude.return_value = "Done."

        try:
            # Create a file to simulate Claude's work
            src_dir = initialized_weld / "src"
            src_dir.mkdir(exist_ok=True)
            test_file = src_dir / "module.py"

            def create_file(*args, **kwargs):
                test_file.write_text("# New module\n")

            mock_claude.side_effect = create_file

            result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

            assert result.exit_code == 0

            # Verify registry created
            registry_path = initialized_weld / ".weld" / "sessions" / "registry.jsonl"
            assert registry_path.exists()

            # Verify activity recorded
            registry = SessionRegistry(registry_path)
            sessions = list(registry.sessions.values())
            assert len(sessions) == 1
            assert sessions[0].activities[0].command == "implement"

        finally:
            # Cleanup
            import shutil

            if claude_dir.exists():
                shutil.rmtree(claude_dir)

    @pytest.mark.cli
    @patch("weld.commands.implement.run_claude")
    def test_implement_tracks_created_files(
        self,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Implement should record files created during execution."""
        from weld.services.session_detector import encode_project_path
        from weld.services.session_tracker import SessionRegistry

        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Create file

Do this.
""")

        # Setup fake session
        claude_dir = Path.home() / ".claude" / "projects" / encode_project_path(initialized_weld)
        claude_dir.mkdir(parents=True, exist_ok=True)
        session_file = claude_dir / "test-session-xyz789.jsonl"
        session_file.write_text('{"type":"user","message":{"role":"user","content":"test"}}\n')

        # Mock Claude to create a file
        def create_test_file(*args, **kwargs):
            src_dir = initialized_weld / "src"
            src_dir.mkdir(exist_ok=True)
            test_file = src_dir / "new_module.py"
            test_file.write_text("# New module\n")

        mock_claude.side_effect = create_test_file

        try:
            result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

            assert result.exit_code == 0

            # Verify file tracked
            registry_path = initialized_weld / ".weld" / "sessions" / "registry.jsonl"
            registry = SessionRegistry(registry_path)
            activity = next(iter(registry.sessions.values())).activities[0]
            assert "src/new_module.py" in activity.files_created

        finally:
            # Cleanup
            import shutil

            if claude_dir.exists():
                shutil.rmtree(claude_dir)

    @pytest.mark.cli
    @patch("weld.commands.implement.run_claude")
    def test_implement_without_session_skips_tracking(
        self,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Implement should succeed even if no Claude session detected."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Do something

Content here.
""")

        mock_claude.return_value = "Done."

        # Ensure no Claude sessions exist
        claude_base = Path.home() / ".claude" / "projects"
        backup = None
        if claude_base.exists():
            # Temporarily rename
            backup = claude_base.with_name("projects.test_backup")
            claude_base.rename(backup)

        try:
            result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

            # Should succeed
            assert result.exit_code == 0

            # No registry should be created
            registry_path = initialized_weld / ".weld" / "sessions" / "registry.jsonl"
            assert not registry_path.exists()
        finally:
            # Restore
            if backup and backup.exists():
                if claude_base.exists():
                    import shutil

                    shutil.rmtree(claude_base)
                backup.rename(claude_base)

    @pytest.mark.cli
    @patch("weld.commands.implement.run_claude")
    def test_implement_handles_interrupt(
        self,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Implement should mark activity as incomplete on interrupt."""
        from weld.services.session_detector import encode_project_path
        from weld.services.session_tracker import SessionRegistry

        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Do something

Content here.
""")

        # Setup fake session
        claude_dir = Path.home() / ".claude" / "projects" / encode_project_path(initialized_weld)
        claude_dir.mkdir(parents=True, exist_ok=True)
        session_file = claude_dir / "test-session-interrupt.jsonl"
        session_file.write_text('{"type":"user","message":{"role":"user","content":"test"}}\n')

        # Mock run_claude to raise KeyboardInterrupt after creating a file
        def create_file_then_interrupt(*args, **kwargs):
            # Create a file so tracking has something to record
            test_file = initialized_weld / "test.txt"
            test_file.write_text("test")
            raise KeyboardInterrupt()

        mock_claude.side_effect = create_file_then_interrupt

        try:
            # Run implement, expecting interrupt
            runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

            # Verify activity tracked even on interrupt
            registry_path = initialized_weld / ".weld" / "sessions" / "registry.jsonl"
            assert registry_path.exists(), "Registry should be created even on interrupt"

            registry = SessionRegistry(registry_path)
            sessions = list(registry.sessions.values())
            assert len(sessions) > 0, "Session should be tracked even on interrupt"

            activity = sessions[0].activities[0]
            assert activity.completed is False, "Activity should be marked incomplete on interrupt"

        finally:
            # Cleanup
            import shutil

            if claude_dir.exists():
                shutil.rmtree(claude_dir)

    @pytest.mark.unit
    def test_file_snapshot_timeout(self, tmp_path: Path, caplog) -> None:
        """File snapshot should timeout on large repos and log warning."""
        import logging

        from weld.services.session_tracker import get_file_snapshot

        # Create large directory structure to trigger timeout
        # Use nested directories to slow down traversal
        for i in range(100):
            subdir = tmp_path / f"dir{i}"
            subdir.mkdir()
            for j in range(50):  # 100 * 50 = 5000 files total
                (subdir / f"file{j}.txt").write_text("content")

        # Call with very short timeout to ensure it triggers
        with caplog.at_level(logging.WARNING):
            snapshot = get_file_snapshot(tmp_path, timeout=0.001)

        # Should return partial snapshot (not empty, not all files)
        assert isinstance(snapshot, dict)
        # Should have captured some files before timeout
        assert len(snapshot) >= 0
        # Should have less than all 5000 files (proof of timeout)
        assert len(snapshot) < 5000
        # Should log warning about timeout (unless completed on very fast machines)
        assert "timed out" in caplog.text.lower() or len(snapshot) == 5000


class TestImplementNonTTY:
    """Test implement behavior without TTY."""

    @pytest.mark.cli
    @patch("weld.commands.implement.sys")
    def test_implement_interactive_requires_tty(
        self,
        mock_sys: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Interactive mode fails without TTY."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step
""")
        # Mock stdin.isatty to return False (no TTY)
        mock_sys.stdin.isatty.return_value = False

        result = runner.invoke(app, ["implement", str(plan_file)])

        assert result.exit_code == 1
        assert "requires a terminal" in result.output.lower()


class TestImplementNotGitRepo:
    """Test implement behavior outside git repository."""

    @pytest.mark.cli
    @patch("weld.commands.implement.get_repo_root")
    def test_implement_not_in_git_repo(
        self,
        mock_get_repo_root: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Fails with exit code 3 when not in git repository."""
        from weld.services import GitError

        mock_get_repo_root.side_effect = GitError("Not a git repository")

        plan_file = tmp_path / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step
""")

        result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

        assert result.exit_code == 3
        assert "not a git repository" in result.output.lower()


class TestImplementDryRun:
    """Test implement dry run modes."""

    @pytest.mark.cli
    def test_implement_dry_run_phase(self, initialized_weld: Path) -> None:
        """Dry run shows non-interactive phase mode."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Do something
""")
        result = runner.invoke(app, ["--dry-run", "implement", str(plan_file), "--phase", "1"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "phase 1" in result.output.lower()


class TestBuildMenuDisplay:
    """Test _build_menu_display helper function."""

    @pytest.mark.unit
    def test_phase_without_steps(self) -> None:
        """Phase without steps shows correctly."""
        from weld.commands.implement import _build_menu_display
        from weld.core.plan_parser import Phase, Plan

        plan = Plan(path=Path("test.md"))
        phase = Phase(
            number=1,
            title="Standalone Phase",
            content="Do something standalone",
            line_number=0,
            is_complete=False,
            steps=[],
        )
        plan.phases = [phase]

        items = _build_menu_display(plan)

        assert len(items) == 1
        assert "○ Phase 1: Standalone Phase" in items[0]
        # Should not have progress indicator when no steps
        assert "complete]" not in items[0]

    @pytest.mark.unit
    def test_phase_with_mixed_steps(self) -> None:
        """Phase with complete and incomplete steps shows progress."""
        from weld.commands.implement import _build_menu_display
        from weld.core.plan_parser import Phase, Plan, Step

        plan = Plan(path=Path("test.md"))
        phase = Phase(
            number=1,
            title="Test Phase",
            content="",
            line_number=0,
            is_complete=False,
        )
        step1 = Step(number="1.1", title="Done", content="", line_number=1, is_complete=True)
        step2 = Step(number="1.2", title="Pending", content="", line_number=2, is_complete=False)
        phase.steps = [step1, step2]
        plan.phases = [phase]

        items = _build_menu_display(plan)

        assert len(items) == 3
        assert "[1/2 complete]" in items[0]
        assert "✓ Step 1.1" in items[1]
        assert "○ Step 1.2" in items[2]

    @pytest.mark.unit
    def test_complete_phase_shows_checkmark(self) -> None:
        """Complete phase shows checkmark."""
        from weld.commands.implement import _build_menu_display
        from weld.core.plan_parser import Phase, Plan, Step

        plan = Plan(path=Path("test.md"))
        phase = Phase(
            number=1,
            title="Done Phase",
            content="",
            line_number=0,
            is_complete=True,
        )
        step = Step(number="1.1", title="Done", content="", line_number=1, is_complete=True)
        phase.steps = [step]
        plan.phases = [phase]

        items = _build_menu_display(plan)

        assert "✓ Phase 1: Done Phase" in items[0]


class TestHasFileChanges:
    """Test _has_file_changes helper function."""

    @pytest.mark.unit
    def test_detects_changes(self, initialized_weld: Path) -> None:
        """Detects when files have changed."""
        from weld.commands.implement import _has_file_changes

        # Get baseline
        baseline = ""

        # Create a file
        (initialized_weld / "new_file.txt").write_text("content")

        result = _has_file_changes(initialized_weld, baseline)

        assert result is True

    @pytest.mark.unit
    def test_no_changes(self, initialized_weld: Path) -> None:
        """Returns False when no changes."""
        from weld.commands.implement import _has_file_changes
        from weld.services import get_status_porcelain

        baseline = get_status_porcelain(cwd=initialized_weld)

        result = _has_file_changes(initialized_weld, baseline)

        assert result is False

    @pytest.mark.unit
    @patch("weld.commands.implement.get_status_porcelain")
    def test_git_error_returns_true(self, mock_status: MagicMock) -> None:
        """Returns True when git status fails (safe default)."""
        from weld.commands.implement import _has_file_changes
        from weld.services import GitError

        mock_status.side_effect = GitError("Cannot get status")

        result = _has_file_changes(Path("/fake"), "")

        assert result is True


class TestHandleInterrupt:
    """Test signal handler function."""

    @pytest.mark.unit
    def test_handle_interrupt_raises_graceful_exit(self) -> None:
        """Signal handler raises GracefulExit exception."""
        from weld.commands.implement import GracefulExit, _handle_interrupt

        with pytest.raises(GracefulExit):
            _handle_interrupt(2, None)


class TestInteractiveMode:
    """Test interactive mode behaviors."""

    @pytest.mark.cli
    @patch("weld.commands.implement.sys")
    @patch("weld.commands.implement.TerminalMenu")
    @patch("weld.commands.implement.run_claude")
    def test_interactive_exit_on_escape(
        self,
        mock_claude: MagicMock,
        mock_menu: MagicMock,
        mock_sys: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Interactive mode exits cleanly when user presses escape."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step
""")
        mock_sys.stdin.isatty.return_value = True

        # Menu returns None on escape
        mock_menu_instance = MagicMock()
        mock_menu_instance.show.return_value = None
        mock_menu.return_value = mock_menu_instance

        result = runner.invoke(app, ["implement", str(plan_file)])

        assert result.exit_code == 0
        assert "paused" in result.output.lower()
        mock_claude.assert_not_called()

    @pytest.mark.cli
    @patch("weld.commands.implement.sys")
    @patch("weld.commands.implement.TerminalMenu")
    @patch("weld.commands.implement.run_claude")
    def test_interactive_select_complete_step(
        self,
        mock_claude: MagicMock,
        mock_menu: MagicMock,
        mock_sys: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Interactive mode shows message when selecting already complete step."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step **COMPLETE**

### Step 1.2: Second step
""")
        mock_sys.stdin.isatty.return_value = True

        # First select complete step (index 1), then exit (None)
        mock_menu_instance = MagicMock()
        mock_menu_instance.show.side_effect = [1, None]
        mock_menu.return_value = mock_menu_instance

        result = runner.invoke(app, ["implement", str(plan_file)])

        assert result.exit_code == 0
        assert "already complete" in result.output.lower()
        mock_claude.assert_not_called()

    @pytest.mark.cli
    @patch("weld.commands.implement.sys")
    @patch("weld.commands.implement.TerminalMenu")
    @patch("weld.commands.implement.run_claude")
    def test_interactive_select_complete_phase(
        self,
        mock_claude: MagicMock,
        mock_menu: MagicMock,
        mock_sys: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Interactive mode shows message when selecting already complete phase."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test **COMPLETE**

### Step 1.1: First step **COMPLETE**
""")
        mock_sys.stdin.isatty.return_value = True

        # Select phase header (index 0), then exit (None)
        mock_menu_instance = MagicMock()
        mock_menu_instance.show.side_effect = [0, None]
        mock_menu.return_value = mock_menu_instance

        result = runner.invoke(app, ["implement", str(plan_file)])

        assert result.exit_code == 0
        # Can be "already complete" or "already marked complete"
        assert "complete" in result.output.lower()
        mock_claude.assert_not_called()

    @pytest.mark.cli
    @patch("weld.commands.implement.signal")
    @patch("weld.commands.implement.sys")
    @patch("weld.commands.implement.TerminalMenu")
    def test_interactive_graceful_exit_on_interrupt(
        self,
        mock_menu: MagicMock,
        mock_sys: MagicMock,
        mock_signal: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Interactive mode handles GracefulExit from Ctrl+C."""
        from weld.commands.implement import GracefulExit

        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step
""")
        mock_sys.stdin.isatty.return_value = True

        # Menu raises GracefulExit (simulating Ctrl+C)
        mock_menu_instance = MagicMock()
        mock_menu_instance.show.side_effect = GracefulExit()
        mock_menu.return_value = mock_menu_instance

        result = runner.invoke(app, ["implement", str(plan_file)])

        assert result.exit_code == 0
        assert "interrupted" in result.output.lower()

    @pytest.mark.cli
    @patch("weld.commands.implement.sys")
    @patch("weld.commands.implement.TerminalMenu")
    @patch("weld.commands.implement.run_claude")
    def test_interactive_select_phase_executes_steps(
        self,
        mock_claude: MagicMock,
        mock_menu: MagicMock,
        mock_sys: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Selecting phase executes all incomplete steps."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First
Do first.

### Step 1.2: Second
Do second.
""")
        mock_sys.stdin.isatty.return_value = True

        # Select phase header (index 0), which should execute both steps
        # After phase completes, all-complete check exits automatically
        mock_menu_instance = MagicMock()
        mock_menu_instance.show.return_value = 0  # Select phase header
        mock_menu.return_value = mock_menu_instance

        mock_claude.return_value = "Done."

        result = runner.invoke(app, ["implement", str(plan_file)])

        assert result.exit_code == 0
        assert mock_claude.call_count == 2  # Both steps
        updated = plan_file.read_text()
        assert "### Step 1.1: First **COMPLETE**" in updated
        assert "### Step 1.2: Second **COMPLETE**" in updated
        assert "## Phase 1: Test **COMPLETE**" in updated

    @pytest.mark.cli
    @patch("weld.commands.implement.sys")
    @patch("weld.commands.implement.TerminalMenu")
    @patch("weld.commands.implement.run_claude")
    def test_interactive_phase_stops_on_failure(
        self,
        mock_claude: MagicMock,
        mock_menu: MagicMock,
        mock_sys: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Phase execution stops on step failure and shows message."""
        from weld.services import ClaudeError

        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First
Do first.

### Step 1.2: Second
Do second.
""")
        mock_sys.stdin.isatty.return_value = True

        # Select phase, first step succeeds, second fails, then exit
        mock_menu_instance = MagicMock()
        mock_menu_instance.show.side_effect = [0, None]  # Select phase, then exit
        mock_menu.return_value = mock_menu_instance

        mock_claude.side_effect = [None, ClaudeError("Failed")]

        result = runner.invoke(app, ["implement", str(plan_file)])

        assert result.exit_code == 0
        assert "stopped" in result.output.lower() or "paused" in result.output.lower()


class TestPromptAndCommitStep:
    """Test _prompt_and_commit_step function."""

    @pytest.mark.unit
    @patch("weld.commands.implement.get_status_porcelain")
    def test_no_registry_returns_early(
        self,
        mock_status: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Returns early if registry is None."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_commit_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"

        _prompt_and_commit_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
            registry=None,
        )

        # Should return early without checking status
        mock_status.assert_not_called()

    @pytest.mark.unit
    @patch("weld.commands.implement.get_status_porcelain")
    def test_git_status_error_returns_early(
        self,
        mock_status: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Returns early if git status fails."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_commit_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext
        from weld.services import GitError
        from weld.services.session_tracker import SessionRegistry

        mock_status.side_effect = GitError("Status failed")

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"
        registry = SessionRegistry(weld_dir / "sessions" / "registry.jsonl")

        _prompt_and_commit_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
            registry=registry,
        )

        # Should handle error gracefully (no crash)

    @pytest.mark.unit
    @patch("weld.commands.implement.get_status_porcelain")
    def test_no_changes_returns_early(
        self,
        mock_status: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Returns early if no uncommitted changes."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_commit_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext
        from weld.services.session_tracker import SessionRegistry

        mock_status.return_value = ""  # No changes

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"
        registry = SessionRegistry(weld_dir / "sessions" / "registry.jsonl")

        _prompt_and_commit_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
            registry=registry,
        )

        # Should return early (no crash)

    @pytest.mark.unit
    def test_dry_run_shows_intent(self, initialized_weld: Path) -> None:
        """Dry run shows what would happen."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_commit_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext
        from weld.services.session_tracker import SessionRegistry

        # Create a change to detect
        (initialized_weld / "new.txt").write_text("content")

        ctx = OutputContext(console=Console(), dry_run=True)
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"
        registry = SessionRegistry(weld_dir / "sessions" / "registry.jsonl")

        # Should not crash in dry run mode
        _prompt_and_commit_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
            registry=registry,
        )

    @pytest.mark.unit
    @patch("weld.commands.implement.Confirm")
    def test_user_declines_commit(
        self,
        mock_confirm: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Returns early if user declines commit."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_commit_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext
        from weld.services.session_tracker import SessionRegistry

        # Create a change
        (initialized_weld / "new.txt").write_text("content")

        mock_confirm.ask.return_value = False

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"
        registry = SessionRegistry(weld_dir / "sessions" / "registry.jsonl")

        _prompt_and_commit_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
            registry=registry,
        )

        # Should return without error

    @pytest.mark.unit
    @patch("weld.commands.implement.Confirm")
    def test_keyboard_interrupt_skips_commit(
        self,
        mock_confirm: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """KeyboardInterrupt during prompt skips commit gracefully."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_commit_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext
        from weld.services.session_tracker import SessionRegistry

        # Create a change
        (initialized_weld / "new.txt").write_text("content")

        mock_confirm.ask.side_effect = KeyboardInterrupt()

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"
        registry = SessionRegistry(weld_dir / "sessions" / "registry.jsonl")

        # Should not raise, just skip
        _prompt_and_commit_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
            registry=registry,
        )

    @pytest.mark.unit
    @patch("weld.commands.implement.Confirm")
    def test_eof_error_skips_commit(
        self,
        mock_confirm: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """EOFError during prompt skips commit gracefully."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_commit_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext
        from weld.services.session_tracker import SessionRegistry

        # Create a change
        (initialized_weld / "new.txt").write_text("content")

        mock_confirm.ask.side_effect = EOFError()

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"
        registry = SessionRegistry(weld_dir / "sessions" / "registry.jsonl")

        # Should not raise, just skip
        _prompt_and_commit_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
            registry=registry,
        )

    @pytest.mark.unit
    @patch("weld.commands.implement.stage_all")
    @patch("weld.commands.implement.Confirm")
    def test_stage_all_error_continues(
        self,
        mock_confirm: MagicMock,
        mock_stage: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """GitError during staging continues gracefully."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_commit_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext
        from weld.services import GitError
        from weld.services.session_tracker import SessionRegistry

        # Create a change
        (initialized_weld / "new.txt").write_text("content")

        mock_confirm.ask.return_value = True
        mock_stage.side_effect = GitError("Stage failed")

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"
        registry = SessionRegistry(weld_dir / "sessions" / "registry.jsonl")

        # Should not raise
        _prompt_and_commit_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
            registry=registry,
        )

    @pytest.mark.unit
    @patch("weld.commands.implement.get_staged_files")
    @patch("weld.commands.implement.stage_all")
    @patch("weld.commands.implement.Confirm")
    def test_get_staged_files_error_continues(
        self,
        mock_confirm: MagicMock,
        mock_stage: MagicMock,
        mock_get_staged: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """GitError getting staged files continues gracefully."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_commit_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext
        from weld.services import GitError
        from weld.services.session_tracker import SessionRegistry

        # Create a change
        (initialized_weld / "new.txt").write_text("content")

        mock_confirm.ask.return_value = True
        mock_stage.return_value = None
        mock_get_staged.side_effect = GitError("Cannot get staged")

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"
        registry = SessionRegistry(weld_dir / "sessions" / "registry.jsonl")

        # Should not raise
        _prompt_and_commit_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
            registry=registry,
        )

    @pytest.mark.unit
    @patch("weld.commands.implement.run_git")
    @patch("weld.commands.implement.get_staged_files")
    @patch("weld.commands.implement.stage_all")
    @patch("weld.commands.implement.Confirm")
    def test_excludes_weld_files(
        self,
        mock_confirm: MagicMock,
        mock_stage: MagicMock,
        mock_get_staged: MagicMock,
        mock_run_git: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Excludes .weld/ files from commit (except config.toml)."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_commit_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext
        from weld.services.session_tracker import SessionRegistry

        # Create changes including .weld files
        (initialized_weld / "new.txt").write_text("content")

        mock_confirm.ask.return_value = True
        mock_stage.return_value = None
        # First call returns files with .weld metadata, second returns filtered
        mock_get_staged.side_effect = [
            ["new.txt", ".weld/sessions/registry.jsonl"],
            ["new.txt"],
        ]

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"
        registry = SessionRegistry(weld_dir / "sessions" / "registry.jsonl")

        _prompt_and_commit_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
            registry=registry,
        )

        # Should have called run_git to unstage .weld file
        mock_run_git.assert_called()


class TestPromptAndReviewStep:
    """Test _prompt_and_review_step function."""

    @pytest.mark.unit
    def test_dry_run_shows_intent(self, initialized_weld: Path) -> None:
        """Dry run shows what would happen."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_review_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext

        ctx = OutputContext(console=Console(), dry_run=True)
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"

        # Should not crash
        _prompt_and_review_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
        )

    @pytest.mark.unit
    @patch("weld.commands.implement.Confirm")
    def test_user_declines_review(
        self,
        mock_confirm: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Returns early if user declines review."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_review_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext

        mock_confirm.ask.return_value = False

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"

        _prompt_and_review_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
        )

        # Confirm.ask should be called once (for review prompt)
        assert mock_confirm.ask.call_count == 1

    @pytest.mark.unit
    @patch("weld.commands.implement.Confirm")
    def test_keyboard_interrupt_first_prompt(
        self,
        mock_confirm: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """KeyboardInterrupt on first prompt skips gracefully."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_review_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext

        mock_confirm.ask.side_effect = KeyboardInterrupt()

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"

        # Should not raise
        _prompt_and_review_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
        )

    @pytest.mark.unit
    @patch("weld.commands.implement.Confirm")
    def test_keyboard_interrupt_second_prompt(
        self,
        mock_confirm: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """KeyboardInterrupt on apply prompt skips gracefully."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_review_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext

        # First prompt yes, second raises
        mock_confirm.ask.side_effect = [True, KeyboardInterrupt()]

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"

        # Should not raise
        _prompt_and_review_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
        )

    @pytest.mark.unit
    @patch("weld.commands.implement.get_diff")
    @patch("weld.commands.implement.Confirm")
    def test_git_diff_error_returns_early(
        self,
        mock_confirm: MagicMock,
        mock_diff: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """GitError getting diff returns early."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_review_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext
        from weld.services import GitError

        mock_confirm.ask.side_effect = [True, False]  # review=yes, apply=no
        mock_diff.side_effect = GitError("Diff failed")

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"

        # Should not raise
        _prompt_and_review_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
        )

    @pytest.mark.unit
    @patch("weld.commands.implement.get_diff")
    @patch("weld.commands.implement.Confirm")
    def test_empty_diff_returns_early(
        self,
        mock_confirm: MagicMock,
        mock_diff: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Empty diff returns early."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_review_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext

        mock_confirm.ask.side_effect = [True, False]  # review=yes, apply=no
        mock_diff.return_value = ""

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"

        # Should not raise
        _prompt_and_review_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
        )

    @pytest.mark.unit
    @patch("weld.commands.implement.run_claude")
    @patch("weld.commands.implement.get_diff")
    @patch("weld.commands.implement.Confirm")
    def test_review_mode_runs_claude(
        self,
        mock_confirm: MagicMock,
        mock_diff: MagicMock,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Review mode runs Claude and saves findings."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_review_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext

        mock_confirm.ask.side_effect = [True, False]  # review=yes, apply=no
        mock_diff.return_value = "diff content here"
        mock_claude.return_value = "# Review Findings\n\nAll looks good."

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"

        _prompt_and_review_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
        )

        mock_claude.assert_called_once()
        # Verify skip_permissions=True (always enabled)
        assert mock_claude.call_args.kwargs.get("skip_permissions") is True

    @pytest.mark.unit
    @patch("weld.commands.implement.run_claude")
    @patch("weld.commands.implement.get_diff")
    @patch("weld.commands.implement.Confirm")
    def test_apply_mode_runs_claude_with_permissions(
        self,
        mock_confirm: MagicMock,
        mock_diff: MagicMock,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Apply mode runs Claude with skip_permissions=True."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_review_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext

        mock_confirm.ask.side_effect = [True, True]  # review=yes, apply=yes
        mock_diff.return_value = "diff content here"
        mock_claude.return_value = "# Fixes Applied\n\nFixed issues."

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"

        _prompt_and_review_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
        )

        mock_claude.assert_called_once()
        # Verify skip_permissions=True for apply mode
        assert mock_claude.call_args.kwargs.get("skip_permissions") is True

    @pytest.mark.unit
    @patch("weld.commands.implement.run_claude")
    @patch("weld.commands.implement.get_diff")
    @patch("weld.commands.implement.Confirm")
    def test_claude_error_continues(
        self,
        mock_confirm: MagicMock,
        mock_diff: MagicMock,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """ClaudeError during review continues gracefully."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_review_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext
        from weld.services import ClaudeError

        mock_confirm.ask.side_effect = [True, False]
        mock_diff.return_value = "diff content"
        mock_claude.side_effect = ClaudeError("Review failed")

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"

        # Should not raise
        _prompt_and_review_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
        )

    @pytest.mark.unit
    @patch("weld.commands.implement.run_claude")
    @patch("weld.commands.implement.get_diff")
    @patch("weld.commands.implement.Confirm")
    def test_empty_result_continues(
        self,
        mock_confirm: MagicMock,
        mock_diff: MagicMock,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Empty Claude result continues gracefully."""
        from rich.console import Console

        from weld.commands.implement import _prompt_and_review_step
        from weld.config import load_config
        from weld.core.plan_parser import Step
        from weld.output import OutputContext

        mock_confirm.ask.side_effect = [True, False]
        mock_diff.return_value = "diff content"
        mock_claude.return_value = ""

        ctx = OutputContext(console=Console())
        step = Step(number="1.1", title="Test", content="", line_number=0, is_complete=True)
        config = load_config(initialized_weld)
        weld_dir = initialized_weld / ".weld"

        # Should not raise
        _prompt_and_review_step(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=initialized_weld,
            weld_dir=weld_dir,
        )


class TestExecuteStepEdgeCases:
    """Test edge cases in _execute_step."""

    @pytest.mark.cli
    @patch("weld.commands.implement.Confirm")
    @patch("weld.commands.implement.run_claude")
    def test_error_recovery_keyboard_interrupt(
        self,
        mock_claude: MagicMock,
        mock_confirm: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """KeyboardInterrupt during error recovery prompt returns False."""
        from weld.services import ClaudeError

        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Do something

Content here.
""")

        # Create file then fail
        def create_file_then_fail(*args, **kwargs):
            (initialized_weld / "new_file.py").write_text("# New\n")
            raise ClaudeError("Crashed")

        mock_claude.side_effect = create_file_then_fail
        mock_confirm.ask.side_effect = KeyboardInterrupt()

        result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

        assert result.exit_code == 21

    @pytest.mark.cli
    @patch("weld.commands.implement.get_status_porcelain")
    @patch("weld.commands.implement.run_claude")
    def test_baseline_status_error_continues(
        self,
        mock_claude: MagicMock,
        mock_status: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """GitError getting baseline status still allows execution."""
        from weld.services import GitError

        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Do something

Content here.
""")

        # First call fails (baseline), subsequent calls work
        mock_status.side_effect = [GitError("Cannot get status")]
        mock_claude.return_value = "Done."

        result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

        assert result.exit_code == 0

    @pytest.mark.cli
    @patch("weld.commands.implement.detect_current_session")
    @patch("weld.commands.implement.run_claude")
    def test_no_session_warning_with_auto_commit(
        self,
        mock_claude: MagicMock,
        mock_detect: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Shows warning when session not detected with auto-commit enabled."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Do something

Content here.
""")

        mock_claude.return_value = "Done."
        mock_detect.return_value = None

        result = runner.invoke(
            app, ["implement", str(plan_file), "--step", "1.1", "--auto-commit", "--no-review"]
        )

        assert result.exit_code == 0
        assert "could not detect" in result.output.lower()

    @pytest.mark.cli
    @patch("weld.commands.implement.run_claude")
    def test_no_review_flag_skips_review(
        self,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """--no-review flag skips review prompt."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Do something

Content here.
""")

        mock_claude.return_value = "Done."

        result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1", "--no-review"])

        assert result.exit_code == 0
        # Should not see review prompt in output
        assert "review changes" not in result.output.lower()
