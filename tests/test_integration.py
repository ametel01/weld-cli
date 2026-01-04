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
