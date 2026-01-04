"""Tests for Codex integration module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from weld.codex import CodexError, extract_revised_plan, parse_review_json, run_codex


class TestRunCodex:
    """Tests for run_codex function."""

    def test_successful_execution(self) -> None:
        """Successful Codex invocation returns stdout."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Codex response here"
        mock_result.stderr = ""

        with patch("weld.codex.subprocess.run", return_value=mock_result) as mock_run:
            result = run_codex("test prompt")

        assert result == "Codex response here"
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["codex", "-p", "test prompt", "--sandbox", "read-only"]

    def test_with_model_parameter(self) -> None:
        """Model parameter is passed to Codex CLI."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "response"
        mock_result.stderr = ""

        with patch("weld.codex.subprocess.run", return_value=mock_result) as mock_run:
            run_codex("prompt", model="o3")

        call_args = mock_run.call_args[0][0]
        assert "--model" in call_args
        assert "o3" in call_args

    def test_with_custom_sandbox(self) -> None:
        """Custom sandbox mode is used."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "response"
        mock_result.stderr = ""

        with patch("weld.codex.subprocess.run", return_value=mock_result) as mock_run:
            run_codex("prompt", sandbox="network-only")

        call_args = mock_run.call_args[0][0]
        assert "--sandbox" in call_args
        idx = call_args.index("--sandbox")
        assert call_args[idx + 1] == "network-only"

    def test_with_custom_exec_path(self) -> None:
        """Custom exec path is used."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "response"
        mock_result.stderr = ""

        with patch("weld.codex.subprocess.run", return_value=mock_result) as mock_run:
            run_codex("prompt", exec_path="/custom/path/codex")

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "/custom/path/codex"

    def test_timeout_raises_error(self) -> None:
        """Timeout raises CodexError."""
        with (
            patch(
                "weld.codex.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="codex", timeout=600),
            ),
            pytest.raises(CodexError, match="timed out after 600 seconds"),
        ):
            run_codex("prompt")

    def test_custom_timeout(self) -> None:
        """Custom timeout is passed to subprocess."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "response"
        mock_result.stderr = ""

        with patch("weld.codex.subprocess.run", return_value=mock_result) as mock_run:
            run_codex("prompt", timeout=120)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 120

    def test_nonzero_exit_code(self) -> None:
        """Non-zero exit code raises CodexError."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: something went wrong"

        with (
            patch("weld.codex.subprocess.run", return_value=mock_result),
            pytest.raises(CodexError, match="Codex failed"),
        ):
            run_codex("prompt")


class TestParseReviewJson:
    """Tests for parse_review_json function."""

    def test_valid_passing_review(self) -> None:
        """Valid passing review JSON is parsed correctly."""
        review = """# Review
Some review content here.

{"pass":true,"issues":[]}"""

        issues = parse_review_json(review)
        assert issues.pass_ is True
        assert issues.issues == []

    def test_valid_failing_review(self) -> None:
        """Valid failing review with issues is parsed correctly."""
        review = """# Review
Found some problems.

{"pass":false,"issues":[{"severity":"blocker","file":"main.py","hint":"Missing"}]}"""

        issues = parse_review_json(review)
        assert issues.pass_ is False
        assert len(issues.issues) == 1
        assert issues.issues[0].severity == "blocker"
        assert issues.issues[0].file == "main.py"

    def test_empty_output_raises_error(self) -> None:
        """Empty output raises CodexError."""
        with pytest.raises(CodexError, match="Invalid JSON"):
            parse_review_json("")

    def test_invalid_json_raises_error(self) -> None:
        """Invalid JSON on last line raises CodexError."""
        review = """# Review
{invalid json}"""

        with pytest.raises(CodexError, match="Invalid JSON"):
            parse_review_json(review)


class TestExtractRevisedPlan:
    """Tests for extract_revised_plan function."""

    def test_extracts_h2_revised_plan(self) -> None:
        """Extracts content under ## Revised Plan header."""
        output = """# Some Review

## Revised Plan

Step 1: Do something
Step 2: Do another thing

## Other Section

This should not be included."""

        result = extract_revised_plan(output)
        assert "Step 1: Do something" in result
        assert "Step 2: Do another thing" in result
        assert "Other Section" not in result
        assert "This should not be included" not in result

    def test_extracts_h1_revised_plan(self) -> None:
        """Extracts content under # Revised Plan header."""
        output = """Some intro text

# Revised Plan

New step 1
New step 2

# Next Section"""

        result = extract_revised_plan(output)
        assert "New step 1" in result
        assert "New step 2" in result
        assert "Next Section" not in result

    def test_case_insensitive(self) -> None:
        """Header matching is case insensitive."""
        output = """## REVISED PLAN

Content here"""

        result = extract_revised_plan(output)
        assert "Content here" in result

    def test_stops_at_h1_header(self) -> None:
        """Extraction stops at next h1 header."""
        output = """## Revised Plan

Plan content

# Stop Here

After content"""

        result = extract_revised_plan(output)
        assert "Plan content" in result
        assert "Stop Here" not in result
        assert "After content" not in result

    def test_stops_at_h2_header(self) -> None:
        """Extraction stops at next h2 header."""
        output = """## Revised Plan

Plan content

## Stop Here

After content"""

        result = extract_revised_plan(output)
        assert "Plan content" in result
        assert "Stop Here" not in result

    def test_no_revised_plan_raises_error(self) -> None:
        """Missing Revised Plan section raises CodexError."""
        output = """# Some Other Section

Content without revised plan"""

        with pytest.raises(CodexError, match="No 'Revised Plan' section found"):
            extract_revised_plan(output)

    def test_empty_revised_plan_raises_error(self) -> None:
        """Empty Revised Plan section raises CodexError."""
        output = """## Revised Plan
## Next Section"""

        with pytest.raises(CodexError, match="No 'Revised Plan' section found"):
            extract_revised_plan(output)

    def test_extracts_until_end_if_no_next_header(self) -> None:
        """Extracts to end of content if no following header."""
        output = """## Revised Plan

Final content
More final content"""

        result = extract_revised_plan(output)
        assert "Final content" in result
        assert "More final content" in result
