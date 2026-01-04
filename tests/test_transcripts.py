"""Tests for transcript gist generation."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from weld.services.transcripts import TranscriptError, TranscriptResult, run_transcript_gist


class TestTranscriptResult:
    """Tests for TranscriptResult model."""

    def test_default_values(self) -> None:
        """TranscriptResult should have sensible defaults."""
        result = TranscriptResult(raw_output="output")
        assert result.gist_url is None
        assert result.preview_url is None
        assert result.warnings == []

    def test_with_all_fields(self) -> None:
        """TranscriptResult should accept all fields."""
        result = TranscriptResult(
            gist_url="https://gist.github.com/user/abc123",
            preview_url="https://preview.example.com/abc123",
            raw_output="full output",
            warnings=["warning 1"],
        )
        assert result.gist_url == "https://gist.github.com/user/abc123"
        assert result.preview_url == "https://preview.example.com/abc123"
        assert len(result.warnings) == 1


class TestRunTranscriptGist:
    """Tests for run_transcript_gist function."""

    @patch("weld.services.transcripts.subprocess.run")
    def test_successful_execution(self, mock_run: MagicMock) -> None:
        """run_transcript_gist should parse gist URL from output."""
        mock_run.return_value = MagicMock(
            stdout="Gist: https://gist.github.com/user/abc123\n",
            stderr="",
        )

        result = run_transcript_gist()

        assert result.gist_url == "https://gist.github.com/user/abc123"
        mock_run.assert_called_once()

    @patch("weld.services.transcripts.subprocess.run")
    def test_with_preview_url(self, mock_run: MagicMock) -> None:
        """run_transcript_gist should parse preview URL."""
        mock_run.return_value = MagicMock(
            stdout="Gist: https://gist.github.com/user/abc123\nPreview: https://preview.example.com/xyz\n",
            stderr="",
        )

        result = run_transcript_gist()

        assert result.gist_url == "https://gist.github.com/user/abc123"
        assert result.preview_url == "https://preview.example.com/xyz"

    @patch("weld.services.transcripts.subprocess.run")
    def test_public_visibility(self, mock_run: MagicMock) -> None:
        """run_transcript_gist should pass --public flag."""
        mock_run.return_value = MagicMock(stdout="", stderr="")

        run_transcript_gist(visibility="public")

        call_args = mock_run.call_args
        assert "--public" in call_args[0][0]

    @patch("weld.services.transcripts.subprocess.run")
    def test_secret_visibility(self, mock_run: MagicMock) -> None:
        """run_transcript_gist should not pass --public for secret."""
        mock_run.return_value = MagicMock(stdout="", stderr="")

        run_transcript_gist(visibility="secret")

        call_args = mock_run.call_args
        assert "--public" not in call_args[0][0]

    @patch("weld.services.transcripts.subprocess.run")
    def test_custom_exec_path(self, mock_run: MagicMock) -> None:
        """run_transcript_gist should use custom exec path."""
        mock_run.return_value = MagicMock(stdout="", stderr="")

        run_transcript_gist(exec_path="/custom/transcript-tool")

        call_args = mock_run.call_args
        assert call_args[0][0][0] == "/custom/transcript-tool"

    @patch("weld.services.transcripts.subprocess.run")
    def test_timeout(self, mock_run: MagicMock) -> None:
        """run_transcript_gist should raise on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=60)

        with pytest.raises(TranscriptError, match="timed out"):
            run_transcript_gist()

    @patch("weld.services.transcripts.subprocess.run")
    def test_auto_detect_warning(self, mock_run: MagicMock) -> None:
        """run_transcript_gist should capture auto-detect warning."""
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="Could not auto-detect GitHub repo from git config\n",
        )

        result = run_transcript_gist()

        assert "Could not auto-detect GitHub repo" in result.warnings

    @patch("weld.services.transcripts.subprocess.run")
    def test_working_directory(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """run_transcript_gist should use working directory."""
        mock_run.return_value = MagicMock(stdout="", stderr="")

        run_transcript_gist(cwd=tmp_path)

        call_args = mock_run.call_args
        assert call_args[1]["cwd"] == tmp_path

    @patch("weld.services.transcripts.subprocess.run")
    def test_no_urls_in_output(self, mock_run: MagicMock) -> None:
        """run_transcript_gist should handle output with no URLs."""
        mock_run.return_value = MagicMock(
            stdout="Some other output\n",
            stderr="",
        )

        result = run_transcript_gist()

        assert result.gist_url is None
        assert result.preview_url is None
        assert "Some other output" in result.raw_output

    @patch("weld.services.transcripts.subprocess.run")
    def test_custom_timeout(self, mock_run: MagicMock) -> None:
        """run_transcript_gist should use custom timeout."""
        mock_run.return_value = MagicMock(stdout="", stderr="")

        run_transcript_gist(timeout=120)

        call_args = mock_run.call_args
        assert call_args[1]["timeout"] == 120
