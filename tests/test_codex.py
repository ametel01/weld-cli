"""Tests for Codex integration module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from weld.services.codex import (
    CodexError,
    _extract_text_from_codex_json,
    extract_revised_plan,
    parse_review_json,
    run_codex,
)


class TestRunCodex:
    """Tests for run_codex function."""

    def test_successful_execution(self) -> None:
        """Successful Codex invocation returns stdout."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Codex response here"
        mock_result.stderr = ""

        with patch("weld.services.codex.subprocess.run", return_value=mock_result) as mock_run:
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

        with patch("weld.services.codex.subprocess.run", return_value=mock_result) as mock_run:
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

        with patch("weld.services.codex.subprocess.run", return_value=mock_result) as mock_run:
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

        with patch("weld.services.codex.subprocess.run", return_value=mock_result) as mock_run:
            run_codex("prompt", exec_path="/custom/path/codex")

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "/custom/path/codex"

    def test_timeout_raises_error(self) -> None:
        """Timeout raises CodexError."""
        with (
            patch(
                "weld.services.codex.subprocess.run",
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

        with patch("weld.services.codex.subprocess.run", return_value=mock_result) as mock_run:
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
            patch("weld.services.codex.subprocess.run", return_value=mock_result),
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


class TestExtractTextFromCodexJson:
    """Tests for _extract_text_from_codex_json function."""

    def test_item_agent_message_format(self) -> None:
        """Extracts text from item.agent_message events."""
        line = '{"type":"item.agent_message","content":[{"type":"output_text","text":"Hello!"}]}'
        assert _extract_text_from_codex_json(line) == "Hello!"

    def test_turn_completed_format(self) -> None:
        """Extracts text from turn.completed events."""
        line = (
            '{"type":"turn.completed","message":'
            '{"content":[{"type":"output_text","text":"Done!"}]}}'
        )
        assert _extract_text_from_codex_json(line) == "Done!"

    def test_multiple_text_blocks(self) -> None:
        """Joins multiple text blocks."""
        line = (
            '{"type":"item.agent_message","content":['
            '{"type":"output_text","text":"Hello "},'
            '{"type":"output_text","text":"World!"}]}'
        )
        assert _extract_text_from_codex_json(line) == "Hello World!"

    def test_ignores_non_output_text_content(self) -> None:
        """Ignores non-output_text content types."""
        line = (
            '{"type":"item.agent_message","content":['
            '{"type":"tool_call","name":"read"},'
            '{"type":"output_text","text":"Result"}]}'
        )
        assert _extract_text_from_codex_json(line) == "Result"

    def test_returns_none_for_no_text(self) -> None:
        """Returns None when no text content."""
        line = '{"type":"item.tool_use","tool":"read_file"}'
        assert _extract_text_from_codex_json(line) is None

    def test_returns_none_for_invalid_json(self) -> None:
        """Returns None for invalid JSON."""
        assert _extract_text_from_codex_json("not json") is None
        assert _extract_text_from_codex_json("{invalid}") is None

    def test_returns_none_for_empty_content(self) -> None:
        """Returns None when content array is empty."""
        line = '{"type":"item.agent_message","content":[]}'
        assert _extract_text_from_codex_json(line) is None

    def test_returns_none_for_other_event_types(self) -> None:
        """Returns None for event types that don't contain text."""
        line = '{"type":"session.started","session_id":"abc123"}'
        assert _extract_text_from_codex_json(line) is None


class TestRunCodexStreaming:
    """Tests for run_codex streaming mode."""

    def test_streaming_successful_execution(self) -> None:
        """Streaming mode captures output correctly."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.poll.return_value = 0

        stream_lines = [
            '{"type":"item.agent_message","content":[{"type":"output_text","text":"Hello"}]}',
            '{"type":"item.agent_message","content":[{"type":"output_text","text":" World!"}]}',
            "",
        ]
        mock_process.stdout.readline.side_effect = [*stream_lines, ""]
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            patch("weld.services.streaming.sys.stdout.write"),
            patch("weld.services.streaming.sys.stdout.flush"),
        ):
            result = run_codex("test prompt", stream=True)

        assert "Hello" in result
        assert "World!" in result

    def test_streaming_timeout_raises_error(self) -> None:
        """Streaming mode times out and raises CodexError."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None

        def slow_readline() -> str:
            import time

            time.sleep(0.1)
            return '{"type":"session.heartbeat"}'

        mock_process.stdout.readline.side_effect = slow_readline
        mock_process.stderr = MagicMock()

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            patch("weld.services.streaming.sys.stdout.write"),
            patch("weld.services.streaming.sys.stdout.flush"),
            pytest.raises(CodexError, match="timed out after 1 seconds"),
        ):
            run_codex("test prompt", stream=True, timeout=1)

        # Verify process was terminated (called by timeout logic and cleanup)
        assert mock_process.terminate.call_count >= 1

    def test_streaming_process_cleanup_on_error(self) -> None:
        """Streaming mode cleans up process on error."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout.readline.side_effect = Exception("Unexpected error")
        mock_process.stderr = MagicMock()

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            pytest.raises(Exception, match="Unexpected error"),
        ):
            run_codex("test prompt", stream=True)

        mock_process.terminate.assert_called_once()

    def test_streaming_nonzero_exit_code(self) -> None:
        """Streaming mode raises error on non-zero exit code."""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.poll.return_value = 1
        mock_process.stdout.readline.side_effect = [""]
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = "Codex error"

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            pytest.raises(CodexError, match="Codex failed"),
        ):
            run_codex("test prompt", stream=True)

    def test_streaming_uses_json_flag(self) -> None:
        """Streaming mode uses --json flag."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.poll.return_value = 0
        mock_process.stdout.readline.side_effect = [""]
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""

        with patch(
            "weld.services.streaming.subprocess.Popen", return_value=mock_process
        ) as mock_popen:
            run_codex("test prompt", stream=True)

        call_args = mock_popen.call_args[0][0]
        assert "--json" in call_args
