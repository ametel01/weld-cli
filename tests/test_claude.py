"""Tests for Claude integration module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from weld.services.claude import (
    ClaudeError,
    _extract_text_from_stream_json,
    parse_review_json,
    run_claude,
)


class TestRunClaude:
    """Tests for run_claude function."""

    def test_successful_execution(self) -> None:
        """Successful Claude invocation returns stdout."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Claude response here"
        mock_result.stderr = ""

        with patch("weld.services.claude.subprocess.run", return_value=mock_result) as mock_run:
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

        with patch("weld.services.claude.subprocess.run", return_value=mock_result) as mock_run:
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

        with patch("weld.services.claude.subprocess.run", return_value=mock_result) as mock_run:
            run_claude("prompt", exec_path="/custom/path/claude")

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "/custom/path/claude"

    def test_timeout_raises_error(self) -> None:
        """Timeout raises ClaudeError."""
        with (
            patch(
                "weld.services.claude.subprocess.run",
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

        with patch("weld.services.claude.subprocess.run", return_value=mock_result) as mock_run:
            run_claude("prompt", timeout=120)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 120

    def test_executable_not_found(self) -> None:
        """Missing executable raises ClaudeError."""
        with (
            patch("weld.services.claude.subprocess.run", side_effect=FileNotFoundError()),
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
            patch("weld.services.claude.subprocess.run", return_value=mock_result),
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


class TestRunClaudeStreaming:
    """Tests for run_claude streaming mode."""

    def test_streaming_successful_execution(self) -> None:
        """Streaming mode captures output correctly."""
        # Create mock process with streaming JSONL output
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.poll.return_value = 0  # Process has exited

        # Simulate streaming output line by line
        stream_lines = [
            '{"type":"assistant","message":{"content":[{"type":"text","text":"Hello"}]}}',
            '{"type":"assistant","message":{"content":[{"type":"text","text":" World!"}]}}',
            "",  # Empty line signals EOF
        ]
        mock_process.stdout.readline.side_effect = [*stream_lines, ""]
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            patch("weld.services.streaming.sys.stdout.write"),
            patch("weld.services.streaming.sys.stdout.flush"),
        ):
            result = run_claude("test prompt", stream=True)

        # Verify output was captured
        assert "Hello" in result
        assert "World!" in result

    def test_streaming_timeout_raises_error(self) -> None:
        """Streaming mode times out and raises ClaudeError."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process still running

        # Make readline block forever (simulated via side_effect that always returns data)
        def slow_readline() -> str:
            import time

            time.sleep(0.1)  # Small delay to ensure timeout check runs
            return '{"type":"system","message":"waiting..."}'

        mock_process.stdout.readline.side_effect = slow_readline
        mock_process.stderr = MagicMock()

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            patch("weld.services.streaming.sys.stdout.write"),
            patch("weld.services.streaming.sys.stdout.flush"),
            pytest.raises(ClaudeError, match="timed out after 1 seconds"),
        ):
            run_claude("test prompt", stream=True, timeout=1)

        # Verify process was terminated (called by timeout logic and cleanup)
        assert mock_process.terminate.call_count >= 1

    def test_streaming_process_cleanup_on_error(self) -> None:
        """Streaming mode cleans up process on error."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process still running
        mock_process.stdout.readline.side_effect = Exception("Unexpected error")
        mock_process.stderr = MagicMock()

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            pytest.raises(Exception, match="Unexpected error"),
        ):
            run_claude("test prompt", stream=True)

        # Verify cleanup was attempted
        mock_process.terminate.assert_called_once()

    def test_streaming_nonzero_exit_code(self) -> None:
        """Streaming mode raises error on non-zero exit code."""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.poll.return_value = 1

        mock_process.stdout.readline.side_effect = [""]  # EOF immediately
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = "Claude error occurred"

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            pytest.raises(ClaudeError, match="Claude failed"),
        ):
            run_claude("test prompt", stream=True)

    def test_streaming_uses_stream_json_format(self) -> None:
        """Streaming mode uses --output-format stream-json."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.poll.return_value = 0
        mock_process.stdout.readline.side_effect = [""]
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""

        with patch(
            "weld.services.streaming.subprocess.Popen", return_value=mock_process
        ) as mock_popen:
            run_claude("test prompt", stream=True)

        # Verify command includes stream-json format
        call_args = mock_popen.call_args[0][0]
        assert "--output-format" in call_args
        assert "stream-json" in call_args
        assert "--verbose" in call_args


class TestExtractTextFromStreamJson:
    """Tests for _extract_text_from_stream_json function."""

    def test_assistant_message_format(self) -> None:
        """Extracts text from assistant message format."""
        line = '{"type":"assistant","message":{"content":[{"type":"text","text":"Hello!"}]}}'
        assert _extract_text_from_stream_json(line) == "Hello!"

    def test_direct_content_format(self) -> None:
        """Extracts text from direct content format."""
        line = '{"content":[{"type":"text","text":"World!"}]}'
        assert _extract_text_from_stream_json(line) == "World!"

    def test_multiple_text_blocks(self) -> None:
        """Joins multiple text blocks."""
        line = '{"content":[{"type":"text","text":"Hello "},{"type":"text","text":"World!"}]}'
        assert _extract_text_from_stream_json(line) == "Hello World!"

    def test_ignores_non_text_content(self) -> None:
        """Ignores non-text content types."""
        line = '{"content":[{"type":"tool_use","name":"read"},{"type":"text","text":"Done"}]}'
        assert _extract_text_from_stream_json(line) == "Done"

    def test_returns_none_for_no_text(self) -> None:
        """Returns None when no text content."""
        line = '{"type":"system","message":"Starting..."}'
        assert _extract_text_from_stream_json(line) is None

    def test_returns_none_for_invalid_json(self) -> None:
        """Returns None for invalid JSON."""
        assert _extract_text_from_stream_json("not json") is None
        assert _extract_text_from_stream_json("{invalid}") is None

    def test_returns_none_for_empty_content(self) -> None:
        """Returns None when content array is empty."""
        line = '{"content":[]}'
        assert _extract_text_from_stream_json(line) is None
