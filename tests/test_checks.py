"""Tests for checks runner."""

from pathlib import Path

import pytest

from weld.services.checks import ChecksError, run_checks, write_checks


class TestRunChecks:
    """Tests for run_checks function invariants."""

    def test_exit_code_is_zero_for_successful_command(self, tmp_path: Path) -> None:
        """Invariant: Successful commands return exit code 0."""
        output, exit_code = run_checks("echo hello", tmp_path)
        assert exit_code == 0
        assert "hello" in output
        assert "stdout" in output.lower()
        assert "stderr" in output.lower()

    def test_exit_code_is_nonzero_for_failing_command(self, tmp_path: Path) -> None:
        """Invariant: Failing commands return non-zero exit code."""
        output, exit_code = run_checks("false", tmp_path)
        assert exit_code == 1
        assert "1" in output

    def test_exit_code_matches_subprocess_exit_code_exactly(self, tmp_path: Path) -> None:
        """Invariant: Returned exit_code matches actual subprocess exit code."""
        # Use specific exit codes (42, 137) to verify exact match, not just 0/1
        for expected_code in [42, 137, 255]:
            output, exit_code = run_checks(f"sh -c 'exit {expected_code}'", tmp_path)
            assert exit_code == expected_code, f"Expected {expected_code}, got {exit_code}"
            assert f"exit_code: {expected_code}" in output

    def test_raises_checks_error_for_nonexistent_command(self, tmp_path: Path) -> None:
        """Invariant: Non-existent commands raise ChecksError."""
        with pytest.raises(ChecksError, match="Command not found"):
            run_checks("nonexistent_command_xyz", tmp_path)

    def test_raises_checks_error_for_invalid_shell_syntax(self, tmp_path: Path) -> None:
        """Invariant: Invalid shell syntax raises ChecksError."""
        with pytest.raises(ChecksError, match="Invalid command syntax"):
            run_checks("echo 'unclosed quote", tmp_path)

    def test_raises_checks_error_when_command_exceeds_timeout(self, tmp_path: Path) -> None:
        """Invariant: Commands exceeding timeout raise ChecksError."""
        with pytest.raises(ChecksError, match="timed out"):
            run_checks("sleep 10", tmp_path, timeout=1)

    def test_exit_code_is_zero_when_within_custom_timeout(self, tmp_path: Path) -> None:
        """Invariant: Commands completing within timeout succeed."""
        _output, exit_code = run_checks("echo fast", tmp_path, timeout=30)
        assert exit_code == 0

    def test_preserves_quoted_arguments_in_command(self, tmp_path: Path) -> None:
        """Invariant: Quoted arguments are preserved in output."""
        output, exit_code = run_checks("echo 'hello world'", tmp_path)
        assert exit_code == 0
        assert "hello world" in output

    def test_runs_command_in_specified_working_directory(self, tmp_path: Path) -> None:
        """Invariant: Commands run in the specified working directory."""
        output, exit_code = run_checks("pwd", tmp_path)
        assert exit_code == 0
        assert str(tmp_path) in output


class TestWriteChecks:
    """Tests for write_checks function invariants."""

    def test_writes_exact_content_to_specified_file(self, tmp_path: Path) -> None:
        """Invariant: File contains exact content passed to write_checks."""
        output_path = tmp_path / "checks.txt"
        write_checks(output_path, "test output")
        assert output_path.read_text() == "test output"

    def test_creates_parent_directories_if_missing(self, tmp_path: Path) -> None:
        """Invariant: Parent directories are created if they don't exist."""
        output_path = tmp_path / "nested" / "dir" / "checks.txt"
        write_checks(output_path, "test output")
        assert output_path.exists()
        assert output_path.read_text() == "test output"

    def test_overwrites_existing_file_content(self, tmp_path: Path) -> None:
        """Invariant: Existing file content is completely replaced."""
        output_path = tmp_path / "checks.txt"
        output_path.write_text("old content")
        write_checks(output_path, "new content")
        assert output_path.read_text() == "new content"


class TestEdgeCases:
    """Edge case tests for checks module invariants."""

    def test_captures_complete_output_for_large_outputs(self, tmp_path: Path) -> None:
        """Invariant: Large outputs (100KB+) are captured completely."""
        output, exit_code = run_checks("seq 1 10000", tmp_path)
        assert exit_code == 0
        assert "1\n" in output
        assert "10000" in output
        assert len(output) > 40000

    def test_raises_unicode_error_for_binary_output(self, tmp_path: Path) -> None:
        """Invariant: Binary output raises UnicodeDecodeError (text mode)."""
        binary_file = tmp_path / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02\xff\xfe\xfd")

        with pytest.raises(UnicodeDecodeError):
            run_checks(f"cat {binary_file}", tmp_path)

    def test_preserves_utf8_unicode_in_output(self, tmp_path: Path) -> None:
        """Invariant: Valid UTF-8 unicode is preserved in output."""
        output, exit_code = run_checks("echo '你好世界 🎉'", tmp_path)
        assert exit_code == 0
        assert "你好世界" in output
        assert "🎉" in output

    def test_preserves_all_lines_in_multiline_output(self, tmp_path: Path) -> None:
        """Invariant: All lines in multiline output are preserved."""
        output, exit_code = run_checks("printf 'line1\\nline2\\nline3'", tmp_path)
        assert exit_code == 0
        assert "line1" in output
        assert "line2" in output
        assert "line3" in output
