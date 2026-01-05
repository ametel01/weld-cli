"""Integration tests for full weld workflows."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from weld.cli import app


@pytest.mark.slow
class TestFullWorkflow:
    """Test complete weld workflow from init to step selection."""

    def test_init_to_run_workflow(
        self,
        runner: CliRunner,
        temp_git_repo: Path,
    ) -> None:
        """Test workflow: init -> run -> list."""
        # Create spec file
        spec_path = temp_git_repo / "spec.md"
        spec_path.write_text("""# Test Spec

## Requirements
- Create hello.py with greet() function
""")

        # Initialize weld (manually since tools may be missing)
        weld_dir = temp_git_repo / ".weld"
        weld_dir.mkdir()
        (weld_dir / "runs").mkdir()
        (weld_dir / "config.toml").write_text("""[project]
name = "test"
[checks]
command = "echo ok"
[codex]
exec = "echo"
[claude]
exec = "echo"
""")

        # Start a run
        result = runner.invoke(app, ["run", "--spec", str(spec_path)])
        assert result.exit_code == 0
        assert "Run created" in result.stdout

        # Verify run directory created
        runs = list((weld_dir / "runs").iterdir())
        assert len(runs) == 1

        run_id = runs[0].name

        # List runs
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert run_id in result.stdout

    def test_run_to_step_workflow(
        self,
        runner: CliRunner,
        temp_git_repo: Path,
    ) -> None:
        """Test workflow: run -> plan import -> step select."""
        # Set up weld
        weld_dir = temp_git_repo / ".weld"
        weld_dir.mkdir()
        (weld_dir / "runs").mkdir()
        (weld_dir / "config.toml").write_text("""[project]
name = "test"
[checks]
command = "echo ok"
[codex]
exec = "echo"
[claude]
exec = "echo"
""")

        # Create spec
        spec_path = temp_git_repo / "spec.md"
        spec_path.write_text("# Test Spec\n\nCreate something.")

        # Start run
        result = runner.invoke(app, ["run", "--spec", str(spec_path)])
        assert result.exit_code == 0

        # Get run ID
        runs = list((weld_dir / "runs").iterdir())
        run_id = runs[0].name

        # Create plan file
        plan_path = temp_git_repo / "plan.md"
        plan_path.write_text("""## Step 1: Create module

### Goal
Create the module.

### Changes
- Create src/module.py

### Acceptance criteria
- [ ] Module exists

### Tests
- pytest

## Step 2: Add function

### Goal
Add a function.

### Changes
- Update src/module.py

### Acceptance criteria
- [ ] Function works

### Tests
- pytest
""")

        # Import plan
        result = runner.invoke(app, ["plan", "import", "--run", run_id, "--file", str(plan_path)])
        assert result.exit_code == 0
        assert "Imported plan with 2 steps" in result.stdout

        # Select step 1
        result = runner.invoke(app, ["step", "select", "--run", run_id, "--n", "1"])
        assert result.exit_code == 0
        assert "Selected step 1" in result.stdout

        # Verify step directory created
        run_dir = weld_dir / "runs" / run_id
        steps_dir = run_dir / "steps"
        step_dirs = list(steps_dir.iterdir())
        assert len(step_dirs) == 1
        assert step_dirs[0].name.startswith("01-")


@pytest.mark.slow
class TestPlanParsing:
    """Test plan parsing through CLI."""

    def test_import_strict_plan(self, runner: CliRunner, run_with_plan: tuple[Path, str]) -> None:
        """Importing a strict-format plan should work without warnings."""
        repo_root, _run_id = run_with_plan

        # Create new run for this test
        weld_dir = repo_root / ".weld"
        new_run_id = "20260104-130000-test-import"
        new_run_dir = weld_dir / "runs" / new_run_id
        new_run_dir.mkdir(parents=True)
        (new_run_dir / "plan").mkdir()
        (new_run_dir / "steps").mkdir()

        import json

        meta = {
            "run_id": new_run_id,
            "repo_root": str(repo_root),
            "branch": "master",
            "head_sha": "abc123",
            "config_hash": "hash123",
        }
        (new_run_dir / "meta.json").write_text(json.dumps(meta))

        # Create plan file
        plan_path = repo_root / "strict_plan.md"
        plan_path.write_text("""## Step 1: First step

### Goal
Do the first thing.

### Changes
- Change A

### Acceptance criteria
- [ ] Criterion 1

### Tests
- pytest
""")

        result = runner.invoke(
            app, ["plan", "import", "--run", new_run_id, "--file", str(plan_path)]
        )
        assert result.exit_code == 0
        assert "Imported plan with 1 steps" in result.stdout


@pytest.mark.slow
class TestStepWorkflow:
    """Test step implementation workflow."""

    def test_step_select_creates_prompt(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """Selecting a step should create implementation prompt."""
        repo_root, run_id = run_with_plan

        result = runner.invoke(app, ["step", "select", "--run", run_id, "--n", "1"])
        assert result.exit_code == 0

        # Verify prompt file created
        weld_dir = repo_root / ".weld"
        run_dir = weld_dir / "runs" / run_id
        steps_dir = run_dir / "steps"
        step_dirs = list(steps_dir.iterdir())
        assert len(step_dirs) == 1

        step_dir = step_dirs[0]
        prompt_file = step_dir / "prompt" / "impl.prompt.md"
        assert prompt_file.exists()

        prompt_content = prompt_file.read_text()
        assert "Create hello module" in prompt_content or "Step 1" in prompt_content

    def test_step_select_writes_step_json(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """Selecting a step should write step.json."""
        repo_root, run_id = run_with_plan

        result = runner.invoke(app, ["step", "select", "--run", run_id, "--n", "2"])
        assert result.exit_code == 0

        # Verify step.json created
        weld_dir = repo_root / ".weld"
        run_dir = weld_dir / "runs" / run_id
        steps_dir = run_dir / "steps"

        step_dirs = [d for d in steps_dir.iterdir() if d.name.startswith("02-")]
        assert len(step_dirs) == 1

        step_json = step_dirs[0] / "step.json"
        assert step_json.exists()

        import json

        step_data = json.loads(step_json.read_text())
        assert step_data["n"] == 2
        assert "Add CLI command" in step_data["title"]


class TestErrorRecovery:
    """Test error handling and recovery."""

    def test_run_without_weld_dir(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """Running without .weld directory should give clear error."""
        spec_path = temp_git_repo / "spec.md"
        spec_path.write_text("# Spec\n")

        result = runner.invoke(app, ["run", "--spec", str(spec_path)])
        # Should fail with clear message about missing init
        assert result.exit_code != 0

    def test_step_select_before_plan(self, runner: CliRunner, initialized_weld: Path) -> None:
        """Selecting step without plan should fail gracefully."""
        # Create a run manually
        weld_dir = initialized_weld / ".weld"
        run_id = "20260104-140000-no-plan"
        run_dir = weld_dir / "runs" / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "steps").mkdir()

        import json

        meta = {"run_id": run_id}
        (run_dir / "meta.json").write_text(json.dumps(meta))

        result = runner.invoke(app, ["step", "select", "--run", run_id, "--n", "1"])
        assert result.exit_code == 1
        assert "No plan found" in result.stdout


class TestMultipleRuns:
    """Test handling multiple runs."""

    def test_multiple_runs_listed(self, runner: CliRunner, initialized_weld: Path) -> None:
        """Multiple runs should all be listed."""
        weld_dir = initialized_weld / ".weld"
        runs_dir = weld_dir / "runs"

        # Create multiple runs
        import json

        for i in range(3):
            run_id = f"20260104-12000{i}-run-{i}"
            run_dir = runs_dir / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "meta.json").write_text(json.dumps({"run_id": run_id}))

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "run-0" in result.stdout
        assert "run-1" in result.stdout
        assert "run-2" in result.stdout


@pytest.mark.slow
class TestCLIChecksIntegration:
    """Test integration between CLI commands and checks runner."""

    def test_step_snapshot_writes_checks_output(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """step snapshot should call run_checks and write output to checks.txt."""
        repo_root, run_id = run_with_plan

        # First select a step
        result = runner.invoke(app, ["step", "select", "--run", run_id, "--n", "1"])
        assert result.exit_code == 0

        # Modify an existing tracked file so there's an unstaged diff
        # (capture_diff uses staged=False by default)
        readme = repo_root / "README.md"
        readme.write_text("# Modified\n\nThis is a modified README for testing.\n")

        # Run snapshot
        result = runner.invoke(app, ["step", "snapshot", "--run", run_id, "--n", "1"])
        assert result.exit_code == 0
        assert "Snapshot captured" in result.stdout

        # Verify checks were written with correct format (new multi-category structure)
        weld_dir = repo_root / ".weld"
        run_dir = weld_dir / "runs" / run_id
        step_dirs = [d for d in (run_dir / "steps").iterdir() if d.name.startswith("01-")]
        assert len(step_dirs) == 1

        # Check for summary file (always present) and checks directory
        iter_dir = step_dirs[0] / "iter" / "01"
        summary_file = iter_dir / "checks.summary.json"
        assert summary_file.exists()

        checks_dir = iter_dir / "checks"
        assert checks_dir.exists()

        # In legacy mode (single command), there's a default.txt
        default_checks = checks_dir / "default.txt"
        assert default_checks.exists()

        checks_content = default_checks.read_text()
        # Verify checks output contains expected sections
        assert "exit_code:" in checks_content
        assert "stdout" in checks_content.lower()
        assert "stderr" in checks_content.lower()


class TestCodexJSONParsing:
    """Test JSON parsing from codex-like output."""

    def test_parse_review_json_valid(self) -> None:
        """parse_codex_review should parse valid JSON from last line."""
        from weld.services import parse_codex_review

        review_md = """Here's my review of the changes.

The implementation looks good overall.

Some minor suggestions:
- Consider adding type hints
- Add docstrings

{"pass":true,"issues":[]}"""

        result = parse_codex_review(review_md)
        assert result.pass_ is True
        assert result.issues == []

    def test_parse_review_json_with_issues(self) -> None:
        """parse_codex_review should parse issues correctly."""
        from weld.services import parse_codex_review

        review_md = """Review complete.

Found some issues.

{"pass":false,"issues":[{"severity":"blocker","file":"main.py","hint":"Security vulnerability"}]}"""

        result = parse_codex_review(review_md)
        assert result.pass_ is False
        assert len(result.issues) == 1
        assert result.issues[0].severity == "blocker"
        assert result.issues[0].file == "main.py"
        assert "Security" in result.issues[0].hint

    def test_parse_review_json_multiple_issues(self) -> None:
        """parse_codex_review should handle multiple issues of different severities."""
        from weld.services import parse_codex_review

        issues_json = [
            {"severity": "blocker", "file": "auth.py", "hint": "SQL injection risk"},
            {"severity": "major", "file": "api.py", "hint": "Missing error handling"},
            {"severity": "minor", "file": "utils.py", "hint": "Unused import"},
        ]
        import json

        review_md = f"Review\n\n{json.dumps({'pass': False, 'issues': issues_json})}"

        result = parse_codex_review(review_md)
        assert result.pass_ is False
        assert len(result.issues) == 3

        # Verify each severity is present
        severities = [i.severity for i in result.issues]
        assert "blocker" in severities
        assert "major" in severities
        assert "minor" in severities

    def test_parse_review_json_invalid_raises(self) -> None:
        """parse_codex_review should raise on invalid JSON."""
        from weld.services import parse_codex_review
        from weld.services.codex import CodexError

        review_md = """Review complete.

This is not valid JSON"""

        with pytest.raises(CodexError, match="Invalid JSON"):
            parse_codex_review(review_md)

    def test_parse_review_json_empty_raises(self) -> None:
        """parse_codex_review should raise on empty input.

        Note: Empty string still parses to [''] after split, so it raises
        'Invalid JSON' rather than 'Empty review output'.
        """
        from weld.services import parse_codex_review
        from weld.services.codex import CodexError

        with pytest.raises(CodexError, match="Invalid JSON"):
            parse_codex_review("")


@pytest.mark.slow
class TestStepSelectPromptPath:
    """Test that step select writes prompt to correct path with correct content."""

    def test_prompt_written_to_correct_path(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """step select should write impl.prompt.md to step_dir/prompt/."""
        repo_root, run_id = run_with_plan

        result = runner.invoke(app, ["step", "select", "--run", run_id, "--n", "1"])
        assert result.exit_code == 0

        # Verify exact path structure
        weld_dir = repo_root / ".weld"
        run_dir = weld_dir / "runs" / run_id
        steps_dir = run_dir / "steps"

        # Find step 1 directory
        step1_dirs = [d for d in steps_dir.iterdir() if d.name.startswith("01-")]
        assert len(step1_dirs) == 1
        step_dir = step1_dirs[0]

        # Verify prompt subdirectory exists
        prompt_dir = step_dir / "prompt"
        assert prompt_dir.exists()
        assert prompt_dir.is_dir()

        # Verify impl.prompt.md exists in correct location
        prompt_file = prompt_dir / "impl.prompt.md"
        assert prompt_file.exists()

        # Verify prompt content includes key elements from the step
        content = prompt_file.read_text()
        assert "Step 1" in content
        assert "Create hello module" in content
        # Verify acceptance criteria are included
        assert "Acceptance Criteria" in content
        # Verify checks command is included
        assert "Validation" in content

    def test_step_json_written_to_step_dir(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """step select should write step.json to step directory root."""
        import json

        repo_root, run_id = run_with_plan

        result = runner.invoke(app, ["step", "select", "--run", run_id, "--n", "1"])
        assert result.exit_code == 0

        weld_dir = repo_root / ".weld"
        run_dir = weld_dir / "runs" / run_id
        step1_dirs = [d for d in (run_dir / "steps").iterdir() if d.name.startswith("01-")]
        step_dir = step1_dirs[0]

        step_json = step_dir / "step.json"
        assert step_json.exists()

        data = json.loads(step_json.read_text())
        assert data["n"] == 1
        assert "title" in data
        assert "body_md" in data
        assert "acceptance_criteria" in data


@pytest.mark.slow
class TestRealGitOperations:
    """Integration tests with real git operations (no mocks)."""

    def test_run_captures_real_branch_name(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """weld run should capture the actual git branch name."""
        import json

        # Set up weld
        weld_dir = temp_git_repo / ".weld"
        weld_dir.mkdir()
        (weld_dir / "runs").mkdir()
        (weld_dir / "config.toml").write_text("""[project]
name = "test"
[checks]
command = "echo ok"
[codex]
exec = "echo"
[claude]
exec = "echo"
""")

        # Create spec
        spec_path = temp_git_repo / "spec.md"
        spec_path.write_text("# Test Spec")

        result = runner.invoke(app, ["run", "--spec", str(spec_path)])
        assert result.exit_code == 0

        # Verify meta.json has correct branch
        runs = list((weld_dir / "runs").iterdir())
        meta_file = runs[0] / "meta.json"
        meta = json.loads(meta_file.read_text())

        # Branch should be master or main (depending on git config)
        assert meta["branch"] in ["master", "main"]

    def test_run_captures_real_head_sha(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """weld run should capture the actual HEAD SHA."""
        import json
        import subprocess

        # Get actual HEAD SHA
        actual_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Set up weld
        weld_dir = temp_git_repo / ".weld"
        weld_dir.mkdir()
        (weld_dir / "runs").mkdir()
        (weld_dir / "config.toml").write_text("""[project]
name = "test"
[checks]
command = "echo ok"
[codex]
exec = "echo"
[claude]
exec = "echo"
""")

        spec_path = temp_git_repo / "spec.md"
        spec_path.write_text("# Test Spec")

        result = runner.invoke(app, ["run", "--spec", str(spec_path)])
        assert result.exit_code == 0

        runs = list((weld_dir / "runs").iterdir())
        meta_file = runs[0] / "meta.json"
        meta = json.loads(meta_file.read_text())

        assert meta["head_sha"] == actual_sha

    def test_step_snapshot_captures_real_diff(
        self, runner: CliRunner, run_with_plan: tuple[Path, str]
    ) -> None:
        """step snapshot should capture actual git diff content."""
        repo_root, run_id = run_with_plan

        # Select step first
        result = runner.invoke(app, ["step", "select", "--run", run_id, "--n", "1"])
        assert result.exit_code == 0

        # Make a real file change
        readme = repo_root / "README.md"
        readme.write_text("# Updated README\n\nNew content here.\n")

        # Create a new file too
        new_file = repo_root / "newfile.txt"
        new_file.write_text("This is new content\n")

        # Run snapshot
        result = runner.invoke(app, ["step", "snapshot", "--run", run_id, "--n", "1"])
        assert result.exit_code == 0

        # Verify diff.patch contains actual changes
        weld_dir = repo_root / ".weld"
        run_dir = weld_dir / "runs" / run_id
        step_dirs = [d for d in (run_dir / "steps").iterdir() if d.name.startswith("01-")]
        diff_file = step_dirs[0] / "iter" / "01" / "diff.patch"

        assert diff_file.exists()
        diff_content = diff_file.read_text()

        # Verify actual diff content
        assert "+# Updated README" in diff_content or "Updated README" in diff_content


@pytest.mark.slow
class TestRealChecksExecution:
    """Integration tests with real command execution."""

    def test_step_snapshot_runs_actual_checks_command(
        self, runner: CliRunner, temp_git_repo: Path
    ) -> None:
        """step snapshot should run the actual checks command and capture output."""
        import json

        # Set up weld with a real checks command
        weld_dir = temp_git_repo / ".weld"
        weld_dir.mkdir()
        (weld_dir / "runs").mkdir()
        (weld_dir / "config.toml").write_text("""[project]
name = "test"
[checks]
command = "echo 'checks passed' && echo 'all tests ok'"
[codex]
exec = "echo"
[claude]
exec = "echo"
""")

        # Create run with plan
        run_id = "20260104-150000-test-checks"
        run_dir = weld_dir / "runs" / run_id
        run_dir.mkdir()
        (run_dir / "plan").mkdir()
        (run_dir / "steps").mkdir()

        meta = {"run_id": run_id, "branch": "master", "head_sha": "abc123"}
        (run_dir / "meta.json").write_text(json.dumps(meta))

        plan = """## Step 1: Test
### Goal
Test the checks command.
### Changes
- Test
### Acceptance criteria
- [ ] Works
### Tests
- echo ok
"""
        (run_dir / "plan" / "plan.raw.md").write_text(plan)
        (run_dir / "plan" / "plan.final.md").write_text(plan)

        # Select step
        result = runner.invoke(app, ["step", "select", "--run", run_id, "--n", "1"])
        assert result.exit_code == 0

        # Make a change to trigger diff
        (temp_git_repo / "README.md").write_text("# Modified for test\n")

        # Run snapshot
        result = runner.invoke(app, ["step", "snapshot", "--run", run_id, "--n", "1"])
        assert result.exit_code == 0

        # Verify checks were captured (new multi-category structure)
        step_dirs = [d for d in (run_dir / "steps").iterdir() if d.name.startswith("01-")]
        iter_dir = step_dirs[0] / "iter" / "01"

        checks_dir = iter_dir / "checks"
        assert checks_dir.exists()

        # In legacy mode (single command), there's a default.txt
        default_checks = checks_dir / "default.txt"
        assert default_checks.exists()
        checks_content = default_checks.read_text()

        # Verify real command output was captured
        assert "checks passed" in checks_content
        assert "all tests ok" in checks_content

    def test_checks_command_with_failing_exit_code(
        self, runner: CliRunner, temp_git_repo: Path
    ) -> None:
        """step snapshot should capture non-zero exit codes from checks."""
        import json

        weld_dir = temp_git_repo / ".weld"
        weld_dir.mkdir()
        (weld_dir / "runs").mkdir()
        # Use a command that exits with code 1 (via sh -c for shell operators)
        (weld_dir / "config.toml").write_text("""[project]
name = "test"
[checks]
command = "sh -c 'echo error: test failed; exit 1'"
[codex]
exec = "echo"
[claude]
exec = "echo"
""")

        run_id = "20260104-150001-test-fail"
        run_dir = weld_dir / "runs" / run_id
        run_dir.mkdir()
        (run_dir / "plan").mkdir()
        (run_dir / "steps").mkdir()

        meta = {"run_id": run_id, "branch": "master", "head_sha": "abc123"}
        (run_dir / "meta.json").write_text(json.dumps(meta))

        plan = """## Step 1: Test
### Goal
Test.
### Changes
- Test
### Acceptance criteria
- [ ] Works
### Tests
- test
"""
        (run_dir / "plan" / "plan.raw.md").write_text(plan)
        (run_dir / "plan" / "plan.final.md").write_text(plan)

        runner.invoke(app, ["step", "select", "--run", run_id, "--n", "1"])
        (temp_git_repo / "README.md").write_text("# Modified\n")
        result = runner.invoke(app, ["step", "snapshot", "--run", run_id, "--n", "1"])

        assert result.exit_code == 0  # Snapshot succeeds even if checks fail

        step_dirs = [d for d in (run_dir / "steps").iterdir() if d.name.startswith("01-")]
        iter_dir = step_dirs[0] / "iter" / "01"

        # In legacy mode (single command), there's a default.txt
        checks_dir = iter_dir / "checks"
        default_checks = checks_dir / "default.txt"
        checks_content = default_checks.read_text()

        # Verify error message and exit code captured
        assert "error: test failed" in checks_content
        assert "exit_code: 1" in checks_content


class TestRealDiffOperations:
    """Integration tests for diff capture with real file operations."""

    def test_capture_diff_with_multiple_modified_files(self, temp_git_repo: Path) -> None:
        """capture_diff should capture changes across multiple tracked files."""
        import subprocess

        from weld.services.diff import capture_diff

        # Create and commit additional files first so they become tracked
        (temp_git_repo / "file1.txt").write_text("Original content 1\n")
        (temp_git_repo / "file2.py").write_text("# Original code\n")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add files"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        # Now modify all tracked files
        (temp_git_repo / "README.md").write_text("# Changed README\n")
        (temp_git_repo / "file1.txt").write_text("Modified content 1\n")
        (temp_git_repo / "file2.py").write_text("def hello(): pass\n")

        diff_content, is_nonempty = capture_diff(temp_git_repo)

        assert is_nonempty
        # All changes to tracked files should be captured
        assert "Changed README" in diff_content
        assert "Modified content" in diff_content
        assert "def hello" in diff_content

    def test_capture_diff_with_deleted_content(self, temp_git_repo: Path) -> None:
        """capture_diff should show deleted content."""
        from weld.services.diff import capture_diff

        # README already has "# Test\n" from fixture
        (temp_git_repo / "README.md").write_text("# New Title\n")

        diff_content, is_nonempty = capture_diff(temp_git_repo)

        assert is_nonempty
        # Should show old line removed and new line added
        assert "-# Test" in diff_content
        assert "+# New Title" in diff_content

    def test_capture_diff_with_binary_files_skipped(self, temp_git_repo: Path) -> None:
        """capture_diff should handle binary files gracefully."""
        from weld.services.diff import capture_diff

        # Create a binary file
        (temp_git_repo / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        # Also modify a text file
        (temp_git_repo / "README.md").write_text("# Changed\n")

        diff_content, is_nonempty = capture_diff(temp_git_repo)

        assert is_nonempty
        # Should still have text diff
        assert "Changed" in diff_content
        # Binary files are typically shown as "Binary files differ"
        # or excluded from text diff
