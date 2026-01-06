"""Tests for Claude integration module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from weld.services.claude import (
    ClaudeError,
    _extract_text_from_stream_json,
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

    def test_skip_permissions_flag(self) -> None:
        """skip_permissions adds --dangerously-skip-permissions flag."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "response"
        mock_result.stderr = ""

        with patch("weld.services.claude.subprocess.run", return_value=mock_result) as mock_run:
            run_claude("prompt", skip_permissions=True)

        call_args = mock_run.call_args[0][0]
        assert "--dangerously-skip-permissions" in call_args

    def test_skip_permissions_default_false(self) -> None:
        """By default, skip_permissions is False."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "response"
        mock_result.stderr = ""

        with patch("weld.services.claude.subprocess.run", return_value=mock_result) as mock_run:
            run_claude("prompt")

        call_args = mock_run.call_args[0][0]
        assert "--dangerously-skip-permissions" not in call_args

    def test_timeout_raises_error(self) -> None:
        """Timeout raises ClaudeError."""
        with (
            patch(
                "weld.services.claude.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=1800),
            ),
            pytest.raises(ClaudeError, match="timed out after 1800 seconds"),
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


class TestRunClaudeStreaming:
    """Tests for run_claude streaming mode."""

    def test_streaming_uses_stream_json_format(self) -> None:
        """Streaming mode uses --output-format stream-json."""
        import select as select_module

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.poll.return_value = 0
        mock_process.stdout.fileno.return_value = 1
        mock_process.stdout.read.return_value = ""
        mock_process.stderr.read.return_value = ""

        with (
            patch("weld.services.claude.subprocess.Popen", return_value=mock_process) as mock_popen,
            patch.object(select_module, "select", return_value=([], [], [])),
        ):
            run_claude("test prompt", stream=True)

        call_args = mock_popen.call_args[0][0]
        assert "--output-format" in call_args
        assert "stream-json" in call_args
        assert "--verbose" in call_args

    def test_streaming_successful_execution(self) -> None:
        """Streaming mode captures output correctly."""
        import select as select_module

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout.fileno.return_value = 1

        # Simulate streaming output
        chunks = [
            '{"type":"assistant","message":{"content":[{"type":"text","text":"Hello"}]}}\n',
            '{"type":"assistant","message":{"content":[{"type":"text","text":" World!"}]}}\n',
            "",  # EOF
        ]
        read_call_count = [0]

        def mock_read(size: int) -> str:
            if read_call_count[0] < len(chunks):
                result = chunks[read_call_count[0]]
                read_call_count[0] += 1
                return result
            return ""

        mock_process.stdout.read.side_effect = mock_read
        mock_process.stderr.read.return_value = ""

        # First call returns readable, subsequent calls return empty (process exited)
        poll_returns = [None, None, 0]
        poll_count = [0]

        def mock_poll() -> int | None:
            if poll_count[0] < len(poll_returns):
                result = poll_returns[poll_count[0]]
                poll_count[0] += 1
                return result
            return 0

        mock_process.poll.side_effect = mock_poll

        with (
            patch("weld.services.claude.subprocess.Popen", return_value=mock_process),
            patch.object(select_module, "select", return_value=([1], [], [])),
            patch("weld.services.claude.sys.stdout.write"),
            patch("weld.services.claude.sys.stdout.flush"),
        ):
            result = run_claude("test prompt", stream=True)

        assert "Hello" in result
        assert "World!" in result

    def test_streaming_timeout_terminates_process(self) -> None:
        """Streaming mode terminates process on timeout."""
        import select as select_module
        import time as time_module

        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process never exits
        mock_process.stdout.fileno.return_value = 1
        mock_process.stderr.read.return_value = ""

        time_values = [0, 0, 5, 10]  # Simulate time passing
        with (
            patch("weld.services.claude.subprocess.Popen", return_value=mock_process),
            patch.object(select_module, "select", return_value=([], [], [])),
            patch.object(time_module, "monotonic", side_effect=time_values),
            pytest.raises(ClaudeError, match="timed out after 1 seconds"),
        ):
            run_claude("test prompt", stream=True, timeout=1)

        mock_process.terminate.assert_called()

    def test_streaming_nonzero_exit_code(self) -> None:
        """Streaming mode raises error on non-zero exit code."""
        import select as select_module

        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.poll.return_value = 1  # Process exited with error
        mock_process.stdout.fileno.return_value = 1
        mock_process.stdout.read.return_value = ""
        mock_process.stderr.read.return_value = "Claude error occurred"

        with (
            patch("weld.services.claude.subprocess.Popen", return_value=mock_process),
            patch.object(select_module, "select", return_value=([], [], [])),
            pytest.raises(ClaudeError, match="Claude failed"),
        ):
            run_claude("test prompt", stream=True)

    def test_streaming_executable_not_found(self) -> None:
        """Streaming mode raises error when executable not found."""
        with (
            patch(
                "weld.services.claude.subprocess.Popen",
                side_effect=FileNotFoundError("claude not found"),
            ),
            pytest.raises(ClaudeError, match="not found"),
        ):
            run_claude("test prompt", stream=True)

    def test_streaming_with_model_parameter(self) -> None:
        """Streaming mode passes model parameter."""
        import select as select_module

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.poll.return_value = 0
        mock_process.stdout.fileno.return_value = 1
        mock_process.stdout.read.return_value = ""
        mock_process.stderr.read.return_value = ""

        with (
            patch("weld.services.claude.subprocess.Popen", return_value=mock_process) as mock_popen,
            patch.object(select_module, "select", return_value=([], [], [])),
        ):
            run_claude("test prompt", stream=True, model="claude-sonnet-4-20250514")

        call_args = mock_popen.call_args[0][0]
        assert "--model" in call_args
        assert "claude-sonnet-4-20250514" in call_args

    def test_streaming_with_skip_permissions(self) -> None:
        """Streaming mode passes skip_permissions flag."""
        import select as select_module

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.poll.return_value = 0
        mock_process.stdout.fileno.return_value = 1
        mock_process.stdout.read.return_value = ""
        mock_process.stderr.read.return_value = ""

        with (
            patch("weld.services.claude.subprocess.Popen", return_value=mock_process) as mock_popen,
            patch.object(select_module, "select", return_value=([], [], [])),
        ):
            run_claude("test prompt", stream=True, skip_permissions=True)

        call_args = mock_popen.call_args[0][0]
        assert "--dangerously-skip-permissions" in call_args

    def test_streaming_cleans_up_on_error(self) -> None:
        """Streaming mode cleans up process on unexpected error."""
        import select as select_module

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout.fileno.return_value = 1
        mock_process.stderr = MagicMock()

        with (
            patch("weld.services.claude.subprocess.Popen", return_value=mock_process),
            patch.object(select_module, "select", side_effect=Exception("Unexpected error")),
            pytest.raises(ClaudeError, match="Streaming failed"),
        ):
            run_claude("test prompt", stream=True)

        mock_process.terminate.assert_called()
