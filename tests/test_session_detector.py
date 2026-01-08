"""Tests for session detector service."""

import time
from pathlib import Path
from unittest.mock import patch

from weld.services.session_detector import (
    detect_current_session,
    encode_project_path,
    get_claude_sessions_dir,
    get_session_id,
)


class TestEncodeProjectPath:
    """Tests for encode_project_path function."""

    def test_basic_path(self) -> None:
        """Should encode path by replacing slashes with hyphens."""
        result = encode_project_path(Path("/home/user/project"))
        assert result == "-home-user-project"

    def test_deep_nested_path(self) -> None:
        """Should handle deeply nested paths."""
        result = encode_project_path(Path("/home/user/source/company/project"))
        assert result == "-home-user-source-company-project"

    def test_single_component_path(self) -> None:
        """Should handle single component path."""
        result = encode_project_path(Path("/project"))
        assert result == "-project"

    def test_root_path(self) -> None:
        """Should handle root path."""
        result = encode_project_path(Path("/"))
        # Path("/").resolve() returns "/" which becomes "-"
        assert result.startswith("-")

    def test_resolves_path(self, tmp_path: Path) -> None:
        """Should resolve relative paths."""
        # Create a subdirectory
        subdir = tmp_path / "subproject"
        subdir.mkdir()

        # Use relative path from tmp_path
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            result = encode_project_path(subdir)
            # Result should contain the resolved absolute path
            assert str(tmp_path).replace("/", "-") in result


class TestGetClaudeSessionsDir:
    """Tests for get_claude_sessions_dir function."""

    def test_returns_none_when_dir_not_exists(self, tmp_path: Path) -> None:
        """Should return None when Claude sessions directory doesn't exist."""
        with patch("weld.services.session_detector.Path.home", return_value=tmp_path):
            result = get_claude_sessions_dir(Path("/some/repo"))
            assert result is None

    def test_returns_path_when_exists(self, tmp_path: Path) -> None:
        """Should return path when Claude sessions directory exists."""
        # Create the expected directory structure
        encoded = "-some-repo"
        sessions_dir = tmp_path / ".claude" / "projects" / encoded
        sessions_dir.mkdir(parents=True)

        with patch("weld.services.session_detector.Path.home", return_value=tmp_path):
            result = get_claude_sessions_dir(Path("/some/repo"))
            assert result is not None
            assert result == sessions_dir


class TestDetectCurrentSession:
    """Tests for detect_current_session function."""

    def test_returns_none_when_no_claude_dir(self, tmp_path: Path) -> None:
        """Should return None when ~/.claude doesn't exist."""
        with patch("weld.services.session_detector.Path.home", return_value=tmp_path):
            result = detect_current_session(Path("/some/repo"))
            assert result is None

    def test_returns_none_when_no_sessions(self, tmp_path: Path) -> None:
        """Should return None when sessions directory is empty."""
        sessions_dir = tmp_path / ".claude" / "projects" / "-some-repo"
        sessions_dir.mkdir(parents=True)

        with patch("weld.services.session_detector.Path.home", return_value=tmp_path):
            result = detect_current_session(Path("/some/repo"))
            assert result is None

    def test_excludes_agent_files(self, tmp_path: Path) -> None:
        """Should exclude files starting with 'agent-'."""
        sessions_dir = tmp_path / ".claude" / "projects" / "-some-repo"
        sessions_dir.mkdir(parents=True)

        # Create agent file (should be excluded)
        agent_file = sessions_dir / "agent-abc123.jsonl"
        agent_file.write_text('{"type":"user"}')

        # Create regular session file
        session_file = sessions_dir / "abc-def.jsonl"
        session_file.write_text('{"type":"user"}')

        with patch("weld.services.session_detector.Path.home", return_value=tmp_path):
            result = detect_current_session(Path("/some/repo"))
            assert result is not None
            assert result.name == "abc-def.jsonl"

    def test_excludes_empty_files(self, tmp_path: Path) -> None:
        """Should exclude empty session files."""
        sessions_dir = tmp_path / ".claude" / "projects" / "-some-repo"
        sessions_dir.mkdir(parents=True)

        # Create empty file (should be excluded)
        empty_file = sessions_dir / "empty.jsonl"
        empty_file.write_text("")

        # Create non-empty file
        valid_file = sessions_dir / "valid.jsonl"
        valid_file.write_text('{"type":"user"}')

        with patch("weld.services.session_detector.Path.home", return_value=tmp_path):
            result = detect_current_session(Path("/some/repo"))
            assert result is not None
            assert result.name == "valid.jsonl"

    def test_returns_most_recent_by_mtime(self, tmp_path: Path) -> None:
        """Should return the most recently modified session."""
        sessions_dir = tmp_path / ".claude" / "projects" / "-some-repo"
        sessions_dir.mkdir(parents=True)

        # Create older session
        older = sessions_dir / "older-session.jsonl"
        older.write_text('{"type":"user"}')

        # Small delay to ensure different mtime
        time.sleep(0.01)

        # Create newer session
        newer = sessions_dir / "newer-session.jsonl"
        newer.write_text('{"type":"user"}')

        with patch("weld.services.session_detector.Path.home", return_value=tmp_path):
            result = detect_current_session(Path("/some/repo"))
            assert result is not None
            assert result.name == "newer-session.jsonl"

    def test_only_agent_files_returns_none(self, tmp_path: Path) -> None:
        """Should return None if only agent files exist."""
        sessions_dir = tmp_path / ".claude" / "projects" / "-some-repo"
        sessions_dir.mkdir(parents=True)

        # Create only agent files
        (sessions_dir / "agent-1.jsonl").write_text('{"type":"user"}')
        (sessions_dir / "agent-2.jsonl").write_text('{"type":"user"}')

        with patch("weld.services.session_detector.Path.home", return_value=tmp_path):
            result = detect_current_session(Path("/some/repo"))
            assert result is None

    def test_only_empty_files_returns_none(self, tmp_path: Path) -> None:
        """Should return None if only empty files exist."""
        sessions_dir = tmp_path / ".claude" / "projects" / "-some-repo"
        sessions_dir.mkdir(parents=True)

        # Create only empty files
        (sessions_dir / "empty1.jsonl").write_text("")
        (sessions_dir / "empty2.jsonl").write_text("")

        with patch("weld.services.session_detector.Path.home", return_value=tmp_path):
            result = detect_current_session(Path("/some/repo"))
            assert result is None


class TestGetSessionId:
    """Tests for get_session_id function."""

    def test_extracts_stem(self) -> None:
        """Should extract filename without extension."""
        session_file = Path("/path/to/abc123-def456.jsonl")
        result = get_session_id(session_file)
        assert result == "abc123-def456"

    def test_handles_simple_name(self) -> None:
        """Should handle simple session names."""
        session_file = Path("/path/session.jsonl")
        result = get_session_id(session_file)
        assert result == "session"

    def test_handles_uuid_format(self) -> None:
        """Should handle UUID-formatted session IDs."""
        session_file = Path("/path/1e3e31f9-10e9-44c3-bfc2-d3cbfcbb343a.jsonl")
        result = get_session_id(session_file)
        assert result == "1e3e31f9-10e9-44c3-bfc2-d3cbfcbb343a"
