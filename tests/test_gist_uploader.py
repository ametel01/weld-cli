"""Tests for gist uploader service."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from weld.services.gist_uploader import (
    GistError,
    GistResult,
    generate_gist_description,
    generate_transcript_filename,
    upload_gist,
)


class TestGistResult:
    """Tests for GistResult model."""

    def test_creates_with_required_fields(self) -> None:
        """GistResult should require gist_url and gist_id."""
        result = GistResult(
            gist_url="https://gist.github.com/user/abc123",
            gist_id="abc123",
        )
        assert result.gist_url == "https://gist.github.com/user/abc123"
        assert result.gist_id == "abc123"


class TestUploadGist:
    """Tests for upload_gist function."""

    @patch("weld.services.gist_uploader.subprocess.run")
    def test_successful_upload(self, mock_run: MagicMock) -> None:
        """upload_gist should return GistResult on success."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://gist.github.com/user/abc12345\n",
            stderr="",
        )

        result = upload_gist(
            content="# Test content",
            filename="test.md",
            description="Test description",
        )

        assert result.gist_url == "https://gist.github.com/user/abc12345"
        assert result.gist_id == "abc12345"

    @patch("weld.services.gist_uploader.subprocess.run")
    def test_passes_description(self, mock_run: MagicMock) -> None:
        """upload_gist should pass description to gh CLI."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://gist.github.com/user/abc123\n",
            stderr="",
        )

        upload_gist(
            content="content",
            filename="test.md",
            description="My description",
        )

        call_args = mock_run.call_args[0][0]
        desc_idx = call_args.index("--desc")
        assert call_args[desc_idx + 1] == "My description"

    @patch("weld.services.gist_uploader.subprocess.run")
    def test_passes_filename(self, mock_run: MagicMock) -> None:
        """upload_gist should pass filename to gh CLI."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://gist.github.com/user/abc123\n",
            stderr="",
        )

        upload_gist(
            content="content",
            filename="my-transcript.md",
            description="desc",
        )

        call_args = mock_run.call_args[0][0]
        filename_idx = call_args.index("--filename")
        assert call_args[filename_idx + 1] == "my-transcript.md"

    @patch("weld.services.gist_uploader.subprocess.run")
    def test_public_flag(self, mock_run: MagicMock) -> None:
        """upload_gist should pass --public flag when public=True."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://gist.github.com/user/abc123\n",
            stderr="",
        )

        upload_gist(
            content="content",
            filename="test.md",
            description="desc",
            public=True,
        )

        call_args = mock_run.call_args[0][0]
        assert "--public" in call_args

    @patch("weld.services.gist_uploader.subprocess.run")
    def test_no_public_flag_by_default(self, mock_run: MagicMock) -> None:
        """upload_gist should not pass --public flag by default."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://gist.github.com/user/abc123\n",
            stderr="",
        )

        upload_gist(
            content="content",
            filename="test.md",
            description="desc",
        )

        call_args = mock_run.call_args[0][0]
        assert "--public" not in call_args

    @patch("weld.services.gist_uploader.subprocess.run")
    def test_uses_cwd(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """upload_gist should use working directory."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://gist.github.com/user/abc123\n",
            stderr="",
        )

        upload_gist(
            content="content",
            filename="test.md",
            description="desc",
            cwd=tmp_path,
        )

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == tmp_path

    @patch("weld.services.gist_uploader.subprocess.run")
    def test_uses_timeout(self, mock_run: MagicMock) -> None:
        """upload_gist should use custom timeout."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://gist.github.com/user/abc123\n",
            stderr="",
        )

        upload_gist(
            content="content",
            filename="test.md",
            description="desc",
            timeout=120,
        )

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 120

    @patch("weld.services.gist_uploader.subprocess.run")
    def test_auth_error(self, mock_run: MagicMock) -> None:
        """upload_gist should raise GistError for auth issues."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error: not logged in to any github hosts",
        )

        with pytest.raises(GistError, match="Not authenticated"):
            upload_gist(
                content="content",
                filename="test.md",
                description="desc",
            )

    @patch("weld.services.gist_uploader.subprocess.run")
    def test_auth_error_variant(self, mock_run: MagicMock) -> None:
        """upload_gist should detect auth keyword in error."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error: auth required",
        )

        with pytest.raises(GistError, match="Not authenticated"):
            upload_gist(
                content="content",
                filename="test.md",
                description="desc",
            )

    @patch("weld.services.gist_uploader.subprocess.run")
    def test_general_error(self, mock_run: MagicMock) -> None:
        """upload_gist should raise GistError for general failures."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error: network timeout",
        )

        with pytest.raises(GistError, match="Gist creation failed"):
            upload_gist(
                content="content",
                filename="test.md",
                description="desc",
            )

    @patch("weld.services.gist_uploader.subprocess.run")
    def test_gh_not_found(self, mock_run: MagicMock) -> None:
        """upload_gist should raise GistError when gh not found."""
        mock_run.side_effect = FileNotFoundError()

        with pytest.raises(GistError, match="gh CLI not found"):
            upload_gist(
                content="content",
                filename="test.md",
                description="desc",
            )

    @patch("weld.services.gist_uploader.subprocess.run")
    def test_timeout(self, mock_run: MagicMock) -> None:
        """upload_gist should raise GistError on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=60)

        with pytest.raises(GistError, match="timed out after 60 seconds"):
            upload_gist(
                content="content",
                filename="test.md",
                description="desc",
            )

    @patch("weld.services.gist_uploader.subprocess.run")
    def test_unexpected_output(self, mock_run: MagicMock) -> None:
        """upload_gist should raise GistError for unexpected output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Some unexpected output\n",
            stderr="",
        )

        with pytest.raises(GistError, match="Unexpected gh output"):
            upload_gist(
                content="content",
                filename="test.md",
                description="desc",
            )

    @patch("weld.services.gist_uploader.subprocess.run")
    def test_extracts_gist_id_with_trailing_slash(self, mock_run: MagicMock) -> None:
        """upload_gist should handle URLs with trailing slash."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://gist.github.com/user/abc12345/\n",
            stderr="",
        )

        result = upload_gist(
            content="content",
            filename="test.md",
            description="desc",
        )

        assert result.gist_id == "abc12345"

    @patch("weld.services.gist_uploader.subprocess.run")
    def test_cleans_up_temp_file(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """upload_gist should clean up temp file after upload."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://gist.github.com/user/abc123\n",
            stderr="",
        )

        upload_gist(
            content="content",
            filename="test.md",
            description="desc",
        )

        # Verify temp file was created and deleted
        call_args = mock_run.call_args[0][0]
        temp_path = Path(call_args[3])  # Path to temp file
        assert not temp_path.exists()


class TestGenerateTranscriptFilename:
    """Tests for generate_transcript_filename function."""

    def test_basic_filename(self) -> None:
        """Should generate filename with project and short session ID."""
        result = generate_transcript_filename("my-project", "abc12345678")
        assert result == "my-project-abc12345.md"

    def test_truncates_session_id(self) -> None:
        """Should truncate session ID to 8 characters."""
        result = generate_transcript_filename("proj", "abcdefghijklmnop")
        assert result == "proj-abcdefgh.md"

    def test_sanitizes_project_name(self) -> None:
        """Should sanitize special characters in project name."""
        result = generate_transcript_filename("my project/path", "abc12345")
        assert result == "my-project-path-abc12345.md"

    def test_preserves_valid_characters(self) -> None:
        """Should preserve alphanumeric, dash, and underscore."""
        result = generate_transcript_filename("my_project-1", "abc12345")
        assert result == "my_project-1-abc12345.md"


class TestGenerateGistDescription:
    """Tests for generate_gist_description function."""

    def test_basic_description(self) -> None:
        """Should combine project name and commit subject."""
        result = generate_gist_description("my-project", "Add new feature")
        assert result == "my-project: Add new feature"

    def test_truncates_long_subject(self) -> None:
        """Should truncate commit subject over 60 characters."""
        long_subject = "This is a very long commit message that exceeds the maximum length limit"
        result = generate_gist_description("proj", long_subject)
        assert len(result.split(": ", 1)[1]) == 63  # 60 + "..."
        assert result.endswith("...")

    def test_preserves_short_subject(self) -> None:
        """Should preserve commit subject under 60 characters."""
        result = generate_gist_description("proj", "Short message")
        assert result == "proj: Short message"
        assert "..." not in result

    def test_exactly_60_characters(self) -> None:
        """Should not truncate subject exactly 60 characters."""
        subject = "x" * 60
        result = generate_gist_description("proj", subject)
        assert result == f"proj: {subject}"
        assert "..." not in result
