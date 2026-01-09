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
