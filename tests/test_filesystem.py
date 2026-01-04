"""Tests for filesystem utilities."""

from pathlib import Path

from weld.services.filesystem import (
    dir_exists,
    ensure_directory,
    file_exists,
    read_file,
    read_file_optional,
    write_file,
)


class TestEnsureDirectory:
    """Tests for ensure_directory function."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        """ensure_directory should create the directory."""
        new_dir = tmp_path / "new_dir"
        result = ensure_directory(new_dir)
        assert result == new_dir
        assert new_dir.exists()
        assert new_dir.is_dir()

    def test_creates_nested_directories(self, tmp_path: Path) -> None:
        """ensure_directory should create nested directories."""
        nested = tmp_path / "a" / "b" / "c"
        result = ensure_directory(nested)
        assert result == nested
        assert nested.exists()

    def test_existing_directory(self, tmp_path: Path) -> None:
        """ensure_directory should work for existing directory."""
        existing = tmp_path / "existing"
        existing.mkdir()
        result = ensure_directory(existing)
        assert result == existing
        assert existing.exists()


class TestWriteFile:
    """Tests for write_file function."""

    def test_writes_content(self, tmp_path: Path) -> None:
        """write_file should write content to file."""
        file_path = tmp_path / "test.txt"
        write_file(file_path, "Hello world")
        assert file_path.read_text() == "Hello world"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        """write_file should create parent directories."""
        file_path = tmp_path / "nested" / "dir" / "test.txt"
        write_file(file_path, "content")
        assert file_path.exists()
        assert file_path.read_text() == "content"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        """write_file should overwrite existing file."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("old")
        write_file(file_path, "new")
        assert file_path.read_text() == "new"


class TestReadFile:
    """Tests for read_file function."""

    def test_reads_content(self, tmp_path: Path) -> None:
        """read_file should return file content."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("Hello world")
        assert read_file(file_path) == "Hello world"

    def test_reads_multiline(self, tmp_path: Path) -> None:
        """read_file should read multiline content."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("line1\nline2\nline3")
        assert read_file(file_path) == "line1\nline2\nline3"


class TestReadFileOptional:
    """Tests for read_file_optional function."""

    def test_reads_existing_file(self, tmp_path: Path) -> None:
        """read_file_optional should read existing file."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")
        assert read_file_optional(file_path) == "content"

    def test_returns_default_for_missing(self, tmp_path: Path) -> None:
        """read_file_optional should return default for missing file."""
        file_path = tmp_path / "nonexistent.txt"
        assert read_file_optional(file_path) == ""

    def test_custom_default(self, tmp_path: Path) -> None:
        """read_file_optional should use custom default."""
        file_path = tmp_path / "nonexistent.txt"
        assert read_file_optional(file_path, "fallback") == "fallback"


class TestFileExists:
    """Tests for file_exists function."""

    def test_existing_file(self, tmp_path: Path) -> None:
        """file_exists should return True for existing file."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")
        assert file_exists(file_path) is True

    def test_missing_file(self, tmp_path: Path) -> None:
        """file_exists should return False for missing file."""
        file_path = tmp_path / "nonexistent.txt"
        assert file_exists(file_path) is False

    def test_directory_returns_false(self, tmp_path: Path) -> None:
        """file_exists should return False for directory."""
        assert file_exists(tmp_path) is False


class TestDirExists:
    """Tests for dir_exists function."""

    def test_existing_directory(self, tmp_path: Path) -> None:
        """dir_exists should return True for existing directory."""
        dir_path = tmp_path / "subdir"
        dir_path.mkdir()
        assert dir_exists(dir_path) is True

    def test_missing_directory(self, tmp_path: Path) -> None:
        """dir_exists should return False for missing directory."""
        dir_path = tmp_path / "nonexistent"
        assert dir_exists(dir_path) is False

    def test_file_returns_false(self, tmp_path: Path) -> None:
        """dir_exists should return False for file."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")
        assert dir_exists(file_path) is False
