"""Tests for step processing utilities."""

import re
import string
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from weld.config import ChecksConfig
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


def make_checks_config(command: str = "pytest") -> ChecksConfig:
    """Create a legacy ChecksConfig for testing."""
    return ChecksConfig(command=command)


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
        result = generate_impl_prompt(step, make_checks_config())
        assert "Step 5" in result

    def test_includes_title(self) -> None:
        """Prompt should include step title."""
        step = make_step(title="Create Module")
        result = generate_impl_prompt(step, make_checks_config())
        assert "Create Module" in result

    def test_includes_body(self) -> None:
        """Prompt should include step body."""
        step = make_step(body_md="Implement the feature carefully.")
        result = generate_impl_prompt(step, make_checks_config())
        assert "Implement the feature carefully" in result

    def test_includes_acceptance_criteria(self) -> None:
        """Prompt should include acceptance criteria."""
        step = make_step(acceptance_criteria=["Works correctly", "Handles errors"])
        result = generate_impl_prompt(step, make_checks_config())
        assert "- [ ] Works correctly" in result
        assert "- [ ] Handles errors" in result

    def test_includes_checks_command(self) -> None:
        """Prompt should include checks command."""
        step = make_step()
        result = generate_impl_prompt(step, make_checks_config("make test"))
        assert "make test" in result

    def test_includes_scope_warning(self) -> None:
        """Prompt should include scope boundary warning."""
        step = make_step()
        result = generate_impl_prompt(step, make_checks_config())
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
        result = generate_impl_prompt(step, make_checks_config())
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


class TestEdgeCases:
    """Edge case tests for step processor."""

    def test_special_characters_in_title(self) -> None:
        """Step with special characters in title should be handled correctly."""
        step = make_step(
            title="Handle <script>alert('xss')</script> & other $pecial chars!",
        )
        result = generate_impl_prompt(step, make_checks_config())
        # Title should be preserved exactly (no escaping at this layer)
        assert "Handle <script>" in result
        assert "& other $pecial" in result

    def test_special_characters_in_slug(self, tmp_path: Path) -> None:
        """Step with special characters in slug creates valid directory."""
        # Slugs should typically be sanitized, but test current behavior
        step = make_step(slug="my-step_v2.0")
        result = get_step_dir(tmp_path, step)
        assert result.name == "01-my-step_v2.0"

    def test_unicode_in_title_and_body(self) -> None:
        """Step with unicode characters should be handled correctly."""
        step = make_step(
            title="实现功能 🚀",
            body_md="Create a feature with 日本語 support and emoji 🎉",
        )
        result = generate_impl_prompt(step, make_checks_config())
        assert "实现功能" in result
        assert "🚀" in result
        assert "日本語" in result
        assert "🎉" in result

    def test_very_long_body_md(self) -> None:
        """Step with very long body_md should be included without truncation."""
        # Create a 50KB body
        long_body = "This is a test paragraph.\n" * 2000
        step = make_step(body_md=long_body)
        result = generate_impl_prompt(step, make_checks_config())
        # The full body should be in the prompt
        assert long_body in result
        # Verify approximate size
        assert len(result) > 50000

    def test_many_acceptance_criteria(self) -> None:
        """Step with many acceptance criteria should include all."""
        criteria = [f"Criterion {i}: something must work" for i in range(100)]
        step = make_step(acceptance_criteria=criteria)
        result = generate_impl_prompt(step, make_checks_config())
        # All criteria should be present
        for i in range(100):
            assert f"Criterion {i}" in result

    def test_body_with_markdown_formatting(self) -> None:
        """Step body with markdown formatting should be preserved."""
        body = """## Subsection

Here's a code block:
```python
def hello():
    print("Hello, World!")
```

And a list:
- Item 1
- Item 2

> A blockquote

| Column 1 | Column 2 |
|----------|----------|
| A        | B        |
"""
        step = make_step(body_md=body)
        result = generate_impl_prompt(step, make_checks_config())
        assert "```python" in result
        assert "def hello():" in result
        assert "- Item 1" in result
        assert "> A blockquote" in result
        assert "| Column 1 |" in result

    def test_step_number_boundary_values(self, tmp_path: Path) -> None:
        """Step numbers at boundary values should format correctly."""
        # Test step 0 (edge case, though typically steps start at 1)
        step_0 = make_step(n=0, slug="step-zero")
        assert get_step_dir(tmp_path, step_0).name == "00-step-zero"

        # Test step 99 (max two-digit)
        step_99 = make_step(n=99, slug="step-99")
        assert get_step_dir(tmp_path, step_99).name == "99-step-99"

        # Test step 100 (three digits)
        step_100 = make_step(n=100, slug="step-100")
        assert get_step_dir(tmp_path, step_100).name == "100-step-100"


class TestPropertyBasedPathGeneration:
    """Property-based tests for path generation invariants.

    These tests verify properties that should hold for ANY valid input,
    catching edge cases that manual test cases might miss.
    """

    # Slugs should match typical URL-safe patterns
    slug_strategy = st.text(
        alphabet=string.ascii_lowercase + string.digits + "-_",
        min_size=1,
        max_size=50,
    ).filter(lambda s: s[0] not in "-_" and s[-1] not in "-_")

    @given(
        n=st.integers(min_value=1, max_value=99),
        slug=slug_strategy,
    )
    @settings(max_examples=100)
    def test_step_dir_name_starts_with_zero_padded_number(self, n: int, slug: str) -> None:
        """Step directory name always starts with zero-padded step number."""
        step = make_step(n=n, slug=slug)
        result = get_step_dir(Path("/tmp"), step)
        # Should start with exactly 2 digits for 1-99
        assert result.name.startswith(f"{n:02d}-")

    @given(
        n=st.integers(min_value=1, max_value=999),
        slug=slug_strategy,
    )
    @settings(max_examples=100)
    def test_step_dir_preserves_slug(self, n: int, slug: str) -> None:
        """Step directory name always ends with the exact slug."""
        step = make_step(n=n, slug=slug)
        result = get_step_dir(Path("/tmp"), step)
        # Name should end with the slug
        assert result.name.endswith(f"-{slug}")

    @given(
        n=st.integers(min_value=1, max_value=999),
        slug=slug_strategy,
    )
    @settings(max_examples=100)
    def test_step_dir_format_matches_pattern(self, n: int, slug: str) -> None:
        """Step directory name matches expected pattern: {number}-{slug}."""
        step = make_step(n=n, slug=slug)
        result = get_step_dir(Path("/tmp"), step)
        # Pattern: digits, dash, then the slug
        pattern = rf"^\d+-{re.escape(slug)}$"
        assert re.match(pattern, result.name)

    @given(
        n=st.integers(min_value=1, max_value=999),
        slug=slug_strategy,
    )
    @settings(max_examples=100)
    def test_step_dir_is_under_steps_subdirectory(self, n: int, slug: str) -> None:
        """Step directory is always under 'steps' subdirectory."""
        step = make_step(n=n, slug=slug)
        result = get_step_dir(Path("/tmp"), step)
        assert result.parent.name == "steps"
        assert result.parent.parent == Path("/tmp")

    @given(iter_n=st.integers(min_value=1, max_value=99))
    @settings(max_examples=50)
    def test_iter_dir_name_is_zero_padded(self, iter_n: int) -> None:
        """Iteration directory name is always zero-padded to 2 digits."""
        result = get_iter_dir(Path("/tmp"), iter_n)
        # Should be exactly 2 characters for 1-99
        assert len(result.name) == 2
        assert result.name == f"{iter_n:02d}"

    @given(iter_n=st.integers(min_value=1, max_value=999))
    @settings(max_examples=50)
    def test_iter_dir_is_under_iter_subdirectory(self, iter_n: int) -> None:
        """Iteration directory is always under 'iter' subdirectory."""
        result = get_iter_dir(Path("/tmp"), iter_n)
        assert result.parent.name == "iter"
        assert result.parent.parent == Path("/tmp")

    @given(
        n=st.integers(min_value=1, max_value=99),
        slug=slug_strategy,
    )
    @settings(max_examples=50)
    def test_created_step_dir_matches_get_step_dir(self, n: int, slug: str) -> None:
        """create_step_directory returns same path as get_step_dir."""
        # Use tempfile instead of tmp_path fixture for Hypothesis compatibility
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            step = make_step(n=n, slug=slug)
            expected = get_step_dir(tmp_path, step)
            actual = create_step_directory(tmp_path, step)
            assert actual == expected
            assert actual.exists()

    @given(iter_n=st.integers(min_value=1, max_value=99))
    @settings(max_examples=50)
    def test_created_iter_dir_matches_get_iter_dir(self, iter_n: int) -> None:
        """create_iter_directory returns same path as get_iter_dir."""
        # Use tempfile instead of tmp_path fixture for Hypothesis compatibility
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            expected = get_iter_dir(tmp_path, iter_n)
            actual = create_iter_directory(tmp_path, iter_n)
            assert actual == expected
            assert actual.exists()
