"""Tests for Telegram bot file path validation."""

import os
from pathlib import Path

import pytest

from weld.telegram.config import TelegramConfig, TelegramProject
from weld.telegram.files import (
    PathNotAllowedError,
    PathNotFoundError,
    get_uploads_dir,
    resolve_upload_filename,
    sanitize_filename,
    validate_fetch_path,
    validate_push_path,
)


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a project directory with some files."""
    project = tmp_path / "myproject"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("print('hello')")
    (project / "README.md").write_text("# My Project")
    return project


@pytest.fixture
def config_with_project(project_dir: Path) -> TelegramConfig:
    """Create a config with the test project registered."""
    return TelegramConfig(projects=[TelegramProject(name="myproject", path=project_dir)])


@pytest.mark.unit
class TestValidateFetchPath:
    """Tests for validate_fetch_path function."""

    def test_valid_file_in_project(
        self, project_dir: Path, config_with_project: TelegramConfig
    ) -> None:
        """validate_fetch_path accepts valid file within project."""
        file_path = project_dir / "src" / "main.py"
        result = validate_fetch_path(file_path, config_with_project)
        assert result == file_path.resolve()

    def test_valid_file_with_string_path(
        self, project_dir: Path, config_with_project: TelegramConfig
    ) -> None:
        """validate_fetch_path accepts string paths."""
        file_path = str(project_dir / "README.md")
        result = validate_fetch_path(file_path, config_with_project)
        assert result == Path(file_path).resolve()

    def test_raises_when_file_not_exists(
        self, project_dir: Path, config_with_project: TelegramConfig
    ) -> None:
        """validate_fetch_path raises PathNotFoundError for non-existent files."""
        file_path = project_dir / "nonexistent.py"
        with pytest.raises(PathNotFoundError, match="does not exist"):
            validate_fetch_path(file_path, config_with_project)

    def test_raises_when_no_projects_registered(self, project_dir: Path) -> None:
        """validate_fetch_path raises PathNotAllowedError when no projects configured."""
        config = TelegramConfig()
        file_path = project_dir / "README.md"
        with pytest.raises(PathNotAllowedError, match="No projects registered"):
            validate_fetch_path(file_path, config)

    def test_raises_when_path_outside_project(
        self, tmp_path: Path, config_with_project: TelegramConfig
    ) -> None:
        """validate_fetch_path raises PathNotAllowedError for paths outside project."""
        outside_file = tmp_path / "outside.txt"
        outside_file.write_text("outside content")
        with pytest.raises(PathNotAllowedError, match="not within any registered project"):
            validate_fetch_path(outside_file, config_with_project)

    def test_raises_for_traversal_attempt(
        self, project_dir: Path, tmp_path: Path, config_with_project: TelegramConfig
    ) -> None:
        """validate_fetch_path raises for path traversal attempts."""
        # Create a file outside the project
        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("secret data")

        # Try to access it via traversal
        traversal_path = project_dir / ".." / "secret.txt"
        with pytest.raises(PathNotAllowedError, match="not within any registered project"):
            validate_fetch_path(traversal_path, config_with_project)

    def test_symlink_within_project_allowed(
        self, project_dir: Path, config_with_project: TelegramConfig
    ) -> None:
        """validate_fetch_path allows symlinks that resolve within project."""
        # Create a symlink within the project pointing to another file in project
        target = project_dir / "README.md"
        link = project_dir / "link_to_readme"
        link.symlink_to(target)

        result = validate_fetch_path(link, config_with_project)
        assert result == target.resolve()

    def test_symlink_escaping_project_rejected(
        self, project_dir: Path, tmp_path: Path, config_with_project: TelegramConfig
    ) -> None:
        """validate_fetch_path rejects symlinks that resolve outside project."""
        # Create a file outside the project
        outside_file = tmp_path / "outside_secret.txt"
        outside_file.write_text("secret")

        # Create a symlink inside project pointing outside
        malicious_link = project_dir / "innocent_link"
        malicious_link.symlink_to(outside_file)

        with pytest.raises(PathNotAllowedError, match="not within any registered project"):
            validate_fetch_path(malicious_link, config_with_project)

    def test_multiple_projects_first_match_wins(self, tmp_path: Path) -> None:
        """validate_fetch_path checks all registered projects."""
        # Create two projects
        proj1 = tmp_path / "proj1"
        proj1.mkdir()
        proj2 = tmp_path / "proj2"
        proj2.mkdir()
        (proj2 / "file.txt").write_text("content")

        config = TelegramConfig(
            projects=[
                TelegramProject(name="proj1", path=proj1),
                TelegramProject(name="proj2", path=proj2),
            ]
        )

        # File in proj2 should be found
        result = validate_fetch_path(proj2 / "file.txt", config)
        assert result == (proj2 / "file.txt").resolve()


@pytest.mark.unit
class TestValidatePushPath:
    """Tests for validate_push_path function."""

    def test_valid_existing_file(
        self, project_dir: Path, config_with_project: TelegramConfig
    ) -> None:
        """validate_push_path accepts existing file within project."""
        file_path = project_dir / "README.md"
        result = validate_push_path(file_path, config_with_project)
        assert result == file_path.resolve()

    def test_valid_new_file_in_existing_dir(
        self, project_dir: Path, config_with_project: TelegramConfig
    ) -> None:
        """validate_push_path accepts new file in existing directory."""
        new_file = project_dir / "src" / "newfile.py"
        result = validate_push_path(new_file, config_with_project)
        assert result == new_file.resolve()

    def test_valid_new_file_in_project_root(
        self, project_dir: Path, config_with_project: TelegramConfig
    ) -> None:
        """validate_push_path accepts new file in project root."""
        new_file = project_dir / "newfile.txt"
        result = validate_push_path(new_file, config_with_project)
        assert result == new_file.resolve()

    def test_raises_when_no_projects_registered(self, project_dir: Path) -> None:
        """validate_push_path raises PathNotAllowedError when no projects configured."""
        config = TelegramConfig()
        file_path = project_dir / "newfile.py"
        with pytest.raises(PathNotAllowedError, match="No projects registered"):
            validate_push_path(file_path, config)

    def test_raises_when_path_outside_project(
        self, tmp_path: Path, config_with_project: TelegramConfig
    ) -> None:
        """validate_push_path raises PathNotAllowedError for paths outside project."""
        outside_file = tmp_path / "outside.txt"
        with pytest.raises(PathNotAllowedError, match="not within any registered project"):
            validate_push_path(outside_file, config_with_project)

    def test_raises_for_traversal_attempt(
        self, project_dir: Path, config_with_project: TelegramConfig
    ) -> None:
        """validate_push_path raises for path traversal attempts."""
        traversal_path = project_dir / ".." / "escaped.txt"
        with pytest.raises(PathNotAllowedError, match="not within any registered project"):
            validate_push_path(traversal_path, config_with_project)

    def test_symlink_dir_escaping_rejected(
        self, project_dir: Path, tmp_path: Path, config_with_project: TelegramConfig
    ) -> None:
        """validate_push_path rejects writing through symlink dir that escapes."""
        # Create a directory outside the project
        outside_dir = tmp_path / "outside_dir"
        outside_dir.mkdir()

        # Create a symlink inside project pointing to outside dir
        link_dir = project_dir / "innocent_dir"
        link_dir.symlink_to(outside_dir)

        # Try to push a file through the symlink
        escaped_path = link_dir / "newfile.txt"
        with pytest.raises(PathNotAllowedError, match="not within any registered project"):
            validate_push_path(escaped_path, config_with_project)

    def test_accepts_string_path(
        self, project_dir: Path, config_with_project: TelegramConfig
    ) -> None:
        """validate_push_path accepts string paths."""
        file_path = str(project_dir / "newfile.txt")
        result = validate_push_path(file_path, config_with_project)
        assert result == Path(file_path).resolve()

    def test_new_file_in_nonexistent_subdir(
        self, project_dir: Path, config_with_project: TelegramConfig
    ) -> None:
        """validate_push_path handles new file in non-existent subdirectory."""
        # This tests the non-strict resolution path
        new_file = project_dir / "newdir" / "subdir" / "file.py"
        result = validate_push_path(new_file, config_with_project)
        # The path should resolve within the project
        assert str(result).startswith(str(project_dir.resolve()))


@pytest.mark.unit
class TestPathValidationEdgeCases:
    """Edge case tests for path validation."""

    def test_relative_path_converted_to_absolute(
        self,
        project_dir: Path,
        config_with_project: TelegramConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Relative paths are resolved relative to CWD."""
        # Change to project directory
        monkeypatch.chdir(project_dir)

        # Use relative path
        result = validate_fetch_path("README.md", config_with_project)
        assert result == (project_dir / "README.md").resolve()

    def test_absolute_path_works(
        self, project_dir: Path, config_with_project: TelegramConfig
    ) -> None:
        """Absolute paths work correctly."""
        abs_path = project_dir.resolve() / "README.md"
        result = validate_fetch_path(abs_path, config_with_project)
        assert result == abs_path

    def test_error_message_lists_registered_projects(self, tmp_path: Path) -> None:
        """Error message includes list of registered projects."""
        proj1 = tmp_path / "proj1"
        proj1.mkdir()
        proj2 = tmp_path / "proj2"
        proj2.mkdir()

        config = TelegramConfig(
            projects=[
                TelegramProject(name="proj1", path=proj1),
                TelegramProject(name="proj2", path=proj2),
            ]
        )

        outside = tmp_path / "outside.txt"
        outside.write_text("content")

        with pytest.raises(PathNotAllowedError) as exc_info:
            validate_fetch_path(outside, config)

        # Check both project paths are mentioned in error
        error_msg = str(exc_info.value)
        assert "proj1" in error_msg or str(proj1) in error_msg
        assert "proj2" in error_msg or str(proj2) in error_msg

    @pytest.mark.skipif(os.name == "nt", reason="Symlinks require elevated privileges on Windows")
    def test_circular_symlink_handled(
        self, project_dir: Path, config_with_project: TelegramConfig
    ) -> None:
        """Circular symlinks are handled gracefully."""
        # Create circular symlinks
        link_a = project_dir / "link_a"
        link_b = project_dir / "link_b"

        # Create link_a pointing to link_b (which doesn't exist yet)
        link_a.symlink_to(link_b)
        # Create link_b pointing back to link_a
        link_b.symlink_to(link_a)

        # Should raise appropriate error (either PathNotFoundError or OSError)
        with pytest.raises((PathNotFoundError, OSError)):
            validate_fetch_path(link_a, config_with_project)

    def test_directory_traversal_with_dots(
        self, project_dir: Path, config_with_project: TelegramConfig
    ) -> None:
        """Path with .. components that stays within project is allowed."""
        # Create nested structure
        nested = project_dir / "a" / "b"
        nested.mkdir(parents=True)
        target = project_dir / "README.md"

        # Path that goes down then up but stays in project
        traversal_in_project = nested / ".." / ".." / "README.md"
        result = validate_fetch_path(traversal_in_project, config_with_project)
        assert result == target.resolve()


@pytest.mark.unit
class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_preserves_safe_filename(self) -> None:
        """Preserves alphanumeric filename with extension."""
        assert sanitize_filename("spec.md") == "spec.md"
        assert sanitize_filename("my-file_v2.txt") == "my-file_v2.txt"

    def test_removes_path_separators(self) -> None:
        """Removes path separators from filename."""
        assert sanitize_filename("path/to/file.md") == "path_to_file.md"
        assert sanitize_filename("path\\to\\file.md") == "path_to_file.md"

    def test_removes_traversal_sequences(self) -> None:
        """Removes directory traversal sequences."""
        # After sanitization and stripping leading underscores/dots
        assert sanitize_filename("../../../etc/passwd") == "etc_passwd"
        assert sanitize_filename("..spec.md") == "spec.md"

    def test_removes_dangerous_characters(self) -> None:
        """Removes shell metacharacters and special characters."""
        assert sanitize_filename("file;rm -rf.md") == "file_rm_-rf.md"
        assert sanitize_filename("file`id`.md") == "file_id_.md"
        # Leading underscore stripped, but trailing preserved before extension
        assert sanitize_filename("$(whoami).txt") == "whoami_.txt"

    def test_collapses_multiple_underscores(self) -> None:
        """Collapses consecutive underscores to single underscore."""
        # After removing dangerous chars, consecutive underscores are collapsed
        result = sanitize_filename("file;;;name.md")
        assert "__" not in result

    def test_strips_leading_trailing_underscores_dots(self) -> None:
        """Strips leading/trailing underscores and dots."""
        assert sanitize_filename("___file.md") == "file.md"
        assert sanitize_filename("file.md___") == "file.md"
        assert sanitize_filename("...file.md") == "file.md"

    def test_handles_empty_string(self) -> None:
        """Handles empty filename."""
        assert sanitize_filename("") == "unnamed_file"

    def test_handles_all_dangerous_chars(self) -> None:
        """Handles filename that becomes empty after sanitization."""
        assert sanitize_filename(";;;") == "unnamed_file"
        assert sanitize_filename("...") == "unnamed_file"

    def test_truncates_long_filename(self) -> None:
        """Truncates filenames longer than 200 characters."""
        long_name = "a" * 250 + ".md"
        result = sanitize_filename(long_name)
        assert len(result) <= 200
        # Should preserve extension
        assert result.endswith(".md")

    def test_truncates_without_extension(self) -> None:
        """Truncates filename without extension correctly."""
        long_name = "a" * 250
        result = sanitize_filename(long_name)
        assert len(result) <= 200

    def test_preserves_extension_on_truncation(self) -> None:
        """Preserves file extension when truncating."""
        long_name = "a" * 250 + ".yaml"
        result = sanitize_filename(long_name)
        assert result.endswith(".yaml")

    def test_handles_unicode_characters(self) -> None:
        """Replaces unicode characters with underscores."""
        result = sanitize_filename("файл.md")
        # Unicode chars become underscores, then collapsed and stripped
        # ".md" extension may be stripped if base becomes empty
        # Just verify the result is a valid sanitized filename
        assert result in ("md", "unnamed_file") or result.endswith(".md")


@pytest.mark.unit
class TestResolveUploadFilename:
    """Tests for resolve_upload_filename function (conflict handling)."""

    def test_returns_original_when_no_conflict(self, tmp_path: Path) -> None:
        """Returns original filename when it doesn't exist."""
        uploads_dir = tmp_path / "uploads"
        uploads_dir.mkdir()

        result = resolve_upload_filename(uploads_dir, "spec.md")
        assert result == uploads_dir / "spec.md"

    def test_adds_numeric_suffix_on_conflict(self, tmp_path: Path) -> None:
        """Adds .1 suffix when file exists."""
        uploads_dir = tmp_path / "uploads"
        uploads_dir.mkdir()
        (uploads_dir / "spec.md").write_text("existing")

        result = resolve_upload_filename(uploads_dir, "spec.md")
        assert result == uploads_dir / "spec.1.md"

    def test_increments_suffix_for_multiple_conflicts(self, tmp_path: Path) -> None:
        """Increments suffix for multiple conflicting files."""
        uploads_dir = tmp_path / "uploads"
        uploads_dir.mkdir()
        (uploads_dir / "spec.md").write_text("original")
        (uploads_dir / "spec.1.md").write_text("first conflict")
        (uploads_dir / "spec.2.md").write_text("second conflict")

        result = resolve_upload_filename(uploads_dir, "spec.md")
        assert result == uploads_dir / "spec.3.md"

    def test_handles_file_without_extension(self, tmp_path: Path) -> None:
        """Handles files without extension."""
        uploads_dir = tmp_path / "uploads"
        uploads_dir.mkdir()
        (uploads_dir / "Makefile").write_text("existing")

        result = resolve_upload_filename(uploads_dir, "Makefile")
        assert result == uploads_dir / "Makefile.1"

    def test_handles_multiple_dots_in_filename(self, tmp_path: Path) -> None:
        """Handles filenames with multiple dots (e.g., archive.tar.gz)."""
        uploads_dir = tmp_path / "uploads"
        uploads_dir.mkdir()
        # Note: sanitize_filename handles tar.gz by only using last extension
        (uploads_dir / "archive.tar.gz").write_text("existing")

        result = resolve_upload_filename(uploads_dir, "archive.tar.gz")
        # Should insert numeric suffix before last extension
        assert result == uploads_dir / "archive.tar.1.gz"

    def test_preserves_extension_format(self, tmp_path: Path) -> None:
        """Preserves original extension when adding suffix."""
        uploads_dir = tmp_path / "uploads"
        uploads_dir.mkdir()
        (uploads_dir / "config.yaml").write_text("existing")

        result = resolve_upload_filename(uploads_dir, "config.yaml")
        assert result.suffix == ".yaml"
        assert result.name == "config.1.yaml"

    def test_handles_empty_directory(self, tmp_path: Path) -> None:
        """Works correctly with empty uploads directory."""
        uploads_dir = tmp_path / "uploads"
        uploads_dir.mkdir()

        result = resolve_upload_filename(uploads_dir, "newfile.md")
        assert result == uploads_dir / "newfile.md"
        assert not result.exists()


@pytest.mark.unit
class TestGetUploadsDir:
    """Tests for get_uploads_dir function."""

    def test_creates_uploads_directory(self, tmp_path: Path) -> None:
        """Creates .weld/telegram/uploads directory if it doesn't exist."""
        project_root = tmp_path / "myproject"
        project_root.mkdir()

        result = get_uploads_dir(project_root)

        assert result.exists()
        assert result.is_dir()
        assert result == project_root / ".weld" / "telegram" / "uploads"

    def test_returns_existing_directory(self, tmp_path: Path) -> None:
        """Returns existing uploads directory without error."""
        project_root = tmp_path / "myproject"
        project_root.mkdir()
        uploads_dir = project_root / ".weld" / "telegram" / "uploads"
        uploads_dir.mkdir(parents=True)

        result = get_uploads_dir(project_root)

        assert result == uploads_dir

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Creates all parent directories (.weld/telegram/) if needed."""
        project_root = tmp_path / "myproject"
        project_root.mkdir()

        result = get_uploads_dir(project_root)

        assert (project_root / ".weld").exists()
        assert (project_root / ".weld" / "telegram").exists()
        assert result.exists()

    def test_preserves_existing_files(self, tmp_path: Path) -> None:
        """Doesn't delete existing files in uploads directory."""
        project_root = tmp_path / "myproject"
        project_root.mkdir()
        uploads_dir = project_root / ".weld" / "telegram" / "uploads"
        uploads_dir.mkdir(parents=True)
        existing_file = uploads_dir / "existing.md"
        existing_file.write_text("content")

        get_uploads_dir(project_root)

        assert existing_file.exists()
        assert existing_file.read_text() == "content"
