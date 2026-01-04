"""Tests for step processing utilities."""

from pathlib import Path

from weld.core.step_processor import (
    create_iter_directory,
    create_step_directory,
    generate_fix_prompt,
    generate_impl_prompt,
    generate_review_prompt,
    get_iter_dir,
    get_step_dir,
)
from weld.models import Step


def make_step(
    n: int = 1,
    title: str = "Test Step",
    slug: str = "test-step",
    body_md: str = "Do the thing",
    acceptance_criteria: list[str] | None = None,
    tests: list[str] | None = None,
) -> Step:
    """Create a test step."""
    return Step(
        n=n,
        title=title,
        slug=slug,
        body_md=body_md,
        acceptance_criteria=acceptance_criteria or ["It works"],
        tests=tests or ["pytest"],
    )


class TestGetStepDir:
    """Tests for get_step_dir function."""

    def test_returns_correct_path(self, tmp_path: Path) -> None:
        """get_step_dir should return correctly formatted path."""
        step = make_step(n=1, slug="my-step")
        result = get_step_dir(tmp_path, step)
        assert result == tmp_path / "steps" / "01-my-step"

    def test_pads_step_number(self, tmp_path: Path) -> None:
        """Step number should be zero-padded."""
        step = make_step(n=5, slug="step-five")
        result = get_step_dir(tmp_path, step)
        assert result.name == "05-step-five"

    def test_double_digit_step(self, tmp_path: Path) -> None:
        """Double-digit step numbers should work."""
        step = make_step(n=12, slug="step-twelve")
        result = get_step_dir(tmp_path, step)
        assert result.name == "12-step-twelve"


class TestCreateStepDirectory:
    """Tests for create_step_directory function."""

    def test_creates_directories(self, tmp_path: Path) -> None:
        """create_step_directory should create step structure."""
        step = make_step(n=1, slug="my-step")
        result = create_step_directory(tmp_path, step)

        assert result.exists()
        assert (result / "prompt").exists()
        assert (result / "iter").exists()

    def test_returns_step_dir_path(self, tmp_path: Path) -> None:
        """create_step_directory should return step dir path."""
        step = make_step(n=2, slug="step-two")
        result = create_step_directory(tmp_path, step)
        assert result == tmp_path / "steps" / "02-step-two"


class TestGetIterDir:
    """Tests for get_iter_dir function."""

    def test_returns_correct_path(self, tmp_path: Path) -> None:
        """get_iter_dir should return correctly formatted path."""
        result = get_iter_dir(tmp_path, 1)
        assert result == tmp_path / "iter" / "01"

    def test_pads_iteration_number(self, tmp_path: Path) -> None:
        """Iteration number should be zero-padded."""
        result = get_iter_dir(tmp_path, 5)
        assert result.name == "05"


class TestCreateIterDirectory:
    """Tests for create_iter_directory function."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        """create_iter_directory should create iteration directory."""
        result = create_iter_directory(tmp_path, 1)
        assert result.exists()
        assert result.is_dir()

    def test_returns_iter_dir_path(self, tmp_path: Path) -> None:
        """create_iter_directory should return iter dir path."""
        result = create_iter_directory(tmp_path, 3)
        assert result == tmp_path / "iter" / "03"


class TestGenerateImplPrompt:
    """Tests for generate_impl_prompt function."""

    def test_includes_step_number(self) -> None:
        """Prompt should include step number."""
        step = make_step(n=5)
        result = generate_impl_prompt(step, "pytest")
        assert "Step 5" in result

    def test_includes_title(self) -> None:
        """Prompt should include step title."""
        step = make_step(title="Create Module")
        result = generate_impl_prompt(step, "pytest")
        assert "Create Module" in result

    def test_includes_body(self) -> None:
        """Prompt should include step body."""
        step = make_step(body_md="Implement the feature carefully.")
        result = generate_impl_prompt(step, "pytest")
        assert "Implement the feature carefully" in result

    def test_includes_acceptance_criteria(self) -> None:
        """Prompt should include acceptance criteria."""
        step = make_step(acceptance_criteria=["Works correctly", "Handles errors"])
        result = generate_impl_prompt(step, "pytest")
        assert "- [ ] Works correctly" in result
        assert "- [ ] Handles errors" in result

    def test_includes_checks_command(self) -> None:
        """Prompt should include checks command."""
        step = make_step()
        result = generate_impl_prompt(step, "make test")
        assert "make test" in result

    def test_includes_scope_warning(self) -> None:
        """Prompt should include scope boundary warning."""
        step = make_step()
        result = generate_impl_prompt(step, "pytest")
        assert "Only implement this step" in result

    def test_empty_acceptance_criteria(self) -> None:
        """Prompt with no AC should show empty checklist."""
        step = Step(
            n=1,
            title="Test Step",
            slug="test-step",
            body_md="Do the thing",
            acceptance_criteria=[],
            tests=[],
        )
        result = generate_impl_prompt(step, "pytest")
        # When AC list is empty, the default message is shown
        assert "- [ ] Implementation complete" in result


class TestGenerateFixPrompt:
    """Tests for generate_fix_prompt function."""

    def test_includes_step_and_iteration(self) -> None:
        """Prompt should include step number and iteration."""
        step = make_step(n=3)
        result = generate_fix_prompt(step, {"issues": []}, 2)
        assert "Step 3" in result
        assert "Iteration 3" in result  # iteration + 1

    def test_includes_blocker_issues(self) -> None:
        """Prompt should include blocker issues."""
        issues = {"issues": [{"severity": "blocker", "file": "main.py", "hint": "Fix the bug"}]}
        result = generate_fix_prompt(make_step(), issues, 1)
        assert "Blockers (must fix)" in result
        assert "main.py" in result
        assert "Fix the bug" in result

    def test_includes_major_issues(self) -> None:
        """Prompt should include major issues."""
        issues = {"issues": [{"severity": "major", "file": "utils.py", "hint": "Improve this"}]}
        result = generate_fix_prompt(make_step(), issues, 1)
        assert "Major Issues" in result
        assert "utils.py" in result

    def test_includes_minor_issues(self) -> None:
        """Prompt should include minor issues."""
        issues = {"issues": [{"severity": "minor", "file": "style.py", "hint": "Style fix"}]}
        result = generate_fix_prompt(make_step(), issues, 1)
        assert "Minor Issues" in result
        assert "style.py" in result

    def test_includes_maps_to(self) -> None:
        """Prompt should include maps_to if present."""
        issues = {
            "issues": [{"severity": "blocker", "file": "f.py", "hint": "Fix", "maps_to": "AC1"}]
        }
        result = generate_fix_prompt(make_step(), issues, 1)
        assert "Maps to: AC1" in result

    def test_empty_issues(self) -> None:
        """Prompt with no issues should show default message."""
        result = generate_fix_prompt(make_step(), {"issues": []}, 1)
        assert "No specific issues listed" in result

    def test_includes_scope_warning(self) -> None:
        """Prompt should include scope boundary warning."""
        result = generate_fix_prompt(make_step(), {"issues": []}, 1)
        assert "Fix these issues only" in result


class TestGenerateReviewPrompt:
    """Tests for generate_review_prompt function."""

    def test_includes_step_info(self) -> None:
        """Prompt should include step number and title."""
        step = make_step(n=2, title="Build Feature")
        result = generate_review_prompt(step, "", "")
        assert "Step 2" in result
        assert "Build Feature" in result

    def test_includes_acceptance_criteria(self) -> None:
        """Prompt should include acceptance criteria."""
        step = make_step(acceptance_criteria=["Tests pass", "Linter clean"])
        result = generate_review_prompt(step, "", "")
        assert "- Tests pass" in result
        assert "- Linter clean" in result

    def test_includes_diff(self) -> None:
        """Prompt should include diff."""
        diff = "+added line\n-removed line"
        result = generate_review_prompt(make_step(), diff, "")
        assert "+added line" in result
        assert "-removed line" in result

    def test_includes_checks_output(self) -> None:
        """Prompt should include checks output."""
        checks = "All tests passed\nexit_code: 0"
        result = generate_review_prompt(make_step(), "", checks)
        assert "All tests passed" in result
        assert "exit_code: 0" in result

    def test_includes_json_format(self) -> None:
        """Prompt should include expected JSON format."""
        result = generate_review_prompt(make_step(), "", "")
        assert '"pass":true' in result
        assert '"issues":[]' in result
        assert '"severity":"blocker"' in result

    def test_empty_acceptance_criteria(self) -> None:
        """Prompt with no AC should show default."""
        step = Step(
            n=1,
            title="Test Step",
            slug="test-step",
            body_md="Do the thing",
            acceptance_criteria=[],
            tests=[],
        )
        result = generate_review_prompt(step, "", "")
        assert "- Implementation complete" in result
