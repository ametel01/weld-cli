"""Tests for Claude integration module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from weld.claude import ClaudeError, parse_review_json, run_claude


class TestRunClaude:
    """Tests for run_claude function."""

    def test_successful_execution(self) -> None:
        """Successful Claude invocation returns stdout."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Claude response here"
        mock_result.stderr = ""

        with patch("weld.claude.subprocess.run", return_value=mock_result) as mock_run:
            result = run_claude("test prompt")

        assert result == "Claude response here"
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["claude", "-p", "test prompt", "--output-format", "text"]

    def test_with_model_parameter(self) -> None:
        """Model parameter is passed to Claude CLI."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "response"
        mock_result.stderr = ""

        with patch("weld.claude.subprocess.run", return_value=mock_result) as mock_run:
            run_claude("prompt", model="claude-sonnet-4-20250514")

        call_args = mock_run.call_args[0][0]
        assert "--model" in call_args
        assert "claude-sonnet-4-20250514" in call_args

    def test_with_custom_exec_path(self) -> None:
        """Custom exec path is used."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "response"
        mock_result.stderr = ""

        with patch("weld.claude.subprocess.run", return_value=mock_result) as mock_run:
            run_claude("prompt", exec_path="/custom/path/claude")

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "/custom/path/claude"

    def test_timeout_raises_error(self) -> None:
        """Timeout raises ClaudeError."""
        with (
            patch(
                "weld.claude.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=600),
            ),
            pytest.raises(ClaudeError, match="timed out after 600 seconds"),
        ):
            run_claude("prompt")

    def test_custom_timeout(self) -> None:
        """Custom timeout is passed to subprocess."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "response"
        mock_result.stderr = ""

        with patch("weld.claude.subprocess.run", return_value=mock_result) as mock_run:
            run_claude("prompt", timeout=120)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 120

    def test_executable_not_found(self) -> None:
        """Missing executable raises ClaudeError."""
        with (
            patch("weld.claude.subprocess.run", side_effect=FileNotFoundError()),
            pytest.raises(ClaudeError, match="not found"),
        ):
            run_claude("prompt")

    def test_nonzero_exit_code(self) -> None:
        """Non-zero exit code raises ClaudeError."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: something went wrong"

        with (
            patch("weld.claude.subprocess.run", return_value=mock_result),
            pytest.raises(ClaudeError, match="Claude failed"),
        ):
            run_claude("prompt")


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
        assert issues.issues[0].hint == "Missing"

    def test_multiple_issues(self) -> None:
        """Multiple issues are parsed correctly."""
        issue1 = '{"severity":"blocker","file":"a.py","hint":"Bug"}'
        issue2 = '{"severity":"minor","file":"b.py","hint":"Style"}'
        review = f"""Review text

{{"pass":false,"issues":[{issue1},{issue2}]}}"""

        issues = parse_review_json(review)
        assert len(issues.issues) == 2
        assert issues.issues[0].severity == "blocker"
        assert issues.issues[1].severity == "minor"

    def test_empty_output_raises_error(self) -> None:
        """Empty output raises ClaudeError."""
        with pytest.raises(ClaudeError, match="Invalid JSON"):
            parse_review_json("")

    def test_whitespace_only_raises_error(self) -> None:
        """Whitespace-only output raises ClaudeError."""
        with pytest.raises(ClaudeError, match="Invalid JSON"):
            parse_review_json("   \n\n   ")

    def test_invalid_json_raises_error(self) -> None:
        """Invalid JSON on last line raises ClaudeError."""
        review = """# Review
Not valid JSON at the end
{invalid json}"""

        with pytest.raises(ClaudeError, match="Invalid JSON"):
            parse_review_json(review)

    def test_no_json_on_last_line(self) -> None:
        """Non-JSON last line raises ClaudeError."""
        review = """# Review
Just some text
No JSON here"""

        with pytest.raises(ClaudeError, match="Invalid JSON"):
            parse_review_json(review)
