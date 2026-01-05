"""Tests for shared streaming subprocess utilities."""

from unittest.mock import MagicMock, patch

import pytest

from weld.services.streaming import StreamingError, run_streaming_subprocess


class TestRunStreamingSubprocess:
    """Tests for run_streaming_subprocess function."""

    def test_successful_execution(self) -> None:
        """Captures output correctly from streaming subprocess."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.poll.return_value = 0

        # Simulate streaming output
        stream_lines = ["line1", "line2", ""]
        mock_process.stdout.readline.side_effect = [*stream_lines, ""]
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""

        def extractor(line: str) -> str | None:
            if line.startswith("line"):
                return f"extracted:{line}"
            return None

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            patch("weld.services.streaming.sys.stdout.write"),
            patch("weld.services.streaming.sys.stdout.flush"),
        ):
            result = run_streaming_subprocess(
                cmd=["test", "cmd"],
                text_extractor=extractor,
            )

        assert "extracted:line1" in result
        assert "extracted:line2" in result

    def test_timeout_raises_error(self) -> None:
        """Times out and raises StreamingError."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None

        def slow_readline() -> str:
            import time

            time.sleep(0.1)
            return "keep-alive"

        mock_process.stdout.readline.side_effect = slow_readline
        mock_process.stderr = MagicMock()

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            patch("weld.services.streaming.sys.stdout.write"),
            patch("weld.services.streaming.sys.stdout.flush"),
            pytest.raises(StreamingError, match="timed out after 1 seconds"),
        ):
            run_streaming_subprocess(
                cmd=["test"],
                text_extractor=lambda x: None,
                timeout=1,
            )

        # Terminate is called by timeout logic, then again by cleanup (if process still running)
        assert mock_process.terminate.call_count >= 1

    def test_custom_error_class(self) -> None:
        """Uses custom error class when provided."""

        class CustomError(Exception):
            pass

        mock_process = MagicMock()
        mock_process.poll.return_value = None

        def slow_readline() -> str:
            import time

            time.sleep(0.1)
            return "data"

        mock_process.stdout.readline.side_effect = slow_readline
        mock_process.stderr = MagicMock()

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            patch("weld.services.streaming.sys.stdout.write"),
            patch("weld.services.streaming.sys.stdout.flush"),
            pytest.raises(CustomError, match="MyService timed out"),
        ):
            run_streaming_subprocess(
                cmd=["test"],
                text_extractor=lambda x: None,
                timeout=1,
                error_class=CustomError,
                service_name="MyService",
            )

    def test_process_cleanup_on_error(self) -> None:
        """Cleans up process on unexpected error."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout.readline.side_effect = Exception("Unexpected")
        mock_process.stderr = MagicMock()

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            pytest.raises(Exception, match="Unexpected"),
        ):
            run_streaming_subprocess(
                cmd=["test"],
                text_extractor=lambda x: None,
            )

        mock_process.terminate.assert_called_once()

    def test_nonzero_exit_code(self) -> None:
        """Raises error on non-zero exit code."""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.poll.return_value = 1
        mock_process.stdout.readline.side_effect = [""]
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = "error output"

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            pytest.raises(StreamingError, match=r"Process failed.*error output"),
        ):
            run_streaming_subprocess(
                cmd=["test"],
                text_extractor=lambda x: None,
            )

    def test_writes_to_stdout(self) -> None:
        """Writes extracted text to stdout."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.poll.return_value = 0
        mock_process.stdout.readline.side_effect = ["data", ""]
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            patch("weld.services.streaming.sys.stdout.write") as mock_write,
            patch("weld.services.streaming.sys.stdout.flush") as mock_flush,
        ):
            run_streaming_subprocess(
                cmd=["test"],
                text_extractor=lambda x: f"output:{x}" if x else None,
            )

        # Verify stdout.write was called with extracted text
        mock_write.assert_called()
        mock_flush.assert_called()

    def test_adds_newlines_between_chunks(self) -> None:
        """Adds newlines between text chunks that don't end with newline."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.poll.return_value = 0
        mock_process.stdout.readline.side_effect = ["a", "b", "c", ""]
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            patch("weld.services.streaming.sys.stdout.write"),
            patch("weld.services.streaming.sys.stdout.flush"),
        ):
            result = run_streaming_subprocess(
                cmd=["test"],
                text_extractor=lambda x: x if x else None,
            )

        # Chunks without trailing newlines should have newlines added between them
        assert "\n" in result

    def test_skips_none_from_extractor(self) -> None:
        """Skips lines where extractor returns None."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.poll.return_value = 0
        mock_process.stdout.readline.side_effect = ["skip", "keep", "skip", ""]
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""

        def extractor(line: str) -> str | None:
            return line if line == "keep" else None

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            patch("weld.services.streaming.sys.stdout.write"),
            patch("weld.services.streaming.sys.stdout.flush"),
        ):
            result = run_streaming_subprocess(
                cmd=["test"],
                text_extractor=extractor,
            )

        assert "keep" in result
        assert "skip" not in result

    def test_force_kill_after_terminate_timeout(self) -> None:
        """Force kills process if terminate doesn't work within timeout."""
        import subprocess as real_subprocess

        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process still running
        mock_process.stdout.readline.side_effect = Exception("Error")
        mock_process.stderr = MagicMock()
        # First wait times out, second wait (after kill) succeeds
        mock_process.wait.side_effect = [real_subprocess.TimeoutExpired("cmd", 5), None]

        with (
            patch("weld.services.streaming.subprocess.Popen", return_value=mock_process),
            pytest.raises(Exception, match="Error"),
        ):
            run_streaming_subprocess(
                cmd=["test"],
                text_extractor=lambda x: None,
            )

        # Verify both terminate and kill were called
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()
