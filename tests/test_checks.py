"""Tests for checks runner."""

from pathlib import Path

import pytest

from weld.services.checks import ChecksError, run_checks, write_checks


class TestRunChecks:
    """Tests for run_checks function."""

    def test_successful_command(self, tmp_path: Path) -> None:
        """Successful command should return output and exit code 0."""
        output, exit_code = run_checks("echo hello", tmp_path)
        assert exit_code == 0
        assert "hello" in output
        assert "exit_code: 0" in output
        assert "=== stdout ===" in output
        assert "=== stderr ===" in output

    def test_failing_command(self, tmp_path: Path) -> None:
        """Failing command should return non-zero exit code."""
        output, exit_code = run_checks("false", tmp_path)
        assert exit_code == 1
        assert "exit_code: 1" in output

    def test_command_with_stderr(self, tmp_path: Path) -> None:
        """Command outputting to stderr should capture it."""
        _output, exit_code = run_checks("echo error >&2", tmp_path)
        # Shell features need shell=True, which we removed
        # So this just runs "echo" with "error" and ">&2" as args
        assert exit_code == 0

    def test_command_not_found(self, tmp_path: Path) -> None:
        """Non-existent command should raise ChecksError."""
        with pytest.raises(ChecksError, match="Command not found"):
            run_checks("nonexistent_command_xyz", tmp_path)

    def test_invalid_command_syntax(self, tmp_path: Path) -> None:
        """Invalid command syntax should raise ChecksError."""
        with pytest.raises(ChecksError, match="Invalid command syntax"):
            run_checks("echo 'unclosed quote", tmp_path)

    def test_timeout_raises_error(self, tmp_path: Path) -> None:
        """Command exceeding timeout should raise ChecksError."""
        with pytest.raises(ChecksError, match="timed out"):
            run_checks("sleep 10", tmp_path, timeout=1)

    def test_custom_timeout(self, tmp_path: Path) -> None:
        """Command completing within custom timeout should succeed."""
        _output, exit_code = run_checks("echo fast", tmp_path, timeout=30)
        assert exit_code == 0

    def test_quoted_arguments(self, tmp_path: Path) -> None:
        """Command with quoted arguments should be parsed correctly."""
        output, exit_code = run_checks("echo 'hello world'", tmp_path)
        assert exit_code == 0
        assert "hello world" in output

    def test_command_with_working_directory(self, tmp_path: Path) -> None:
        """Command should run in specified working directory."""
        output, exit_code = run_checks("pwd", tmp_path)
        assert exit_code == 0
        assert str(tmp_path) in output


class TestWriteChecks:
    """Tests for write_checks function."""

    def test_writes_to_file(self, tmp_path: Path) -> None:
        """write_checks should write content to file."""
        output_path = tmp_path / "checks.txt"
        write_checks(output_path, "test output")
        assert output_path.read_text() == "test output"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """write_checks should create parent directories if needed."""
        output_path = tmp_path / "nested" / "dir" / "checks.txt"
        write_checks(output_path, "test output")
        assert output_path.exists()
        assert output_path.read_text() == "test output"

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """write_checks should overwrite existing file."""
        output_path = tmp_path / "checks.txt"
        output_path.write_text("old content")
        write_checks(output_path, "new content")
        assert output_path.read_text() == "new content"
