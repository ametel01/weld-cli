"""Tests for weld.completions module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from weld.completions import (
    _COMPLETION_MARKER,
    _completion_already_in_rc,
    _get_rc_file_path,
    _install_completion_to_rc,
    auto_install_completion,
    complete_export_format,
    complete_markdown_file,
    complete_phase_number,
    complete_step_number,
    complete_task_type,
    detect_shell,
    get_completion_marker_path,
    is_completion_installed,
    mark_completion_installed,
)
from weld.config import TaskType


@pytest.mark.unit
class TestCompleteTaskType:
    """Tests for complete_task_type function."""

    def test_empty_prefix_returns_all_task_types(self) -> None:
        """Empty prefix should return all TaskType values."""
        result = complete_task_type("")
        expected = [t.value for t in TaskType]
        assert sorted(result) == sorted(expected)

    def test_prefix_filters_results(self) -> None:
        """Prefix should filter to matching task types only."""
        result = complete_task_type("research")
        assert "research" in result
        assert "research_review" in result
        assert "discover" not in result
        assert "implementation" not in result

    def test_prefix_case_insensitive(self) -> None:
        """Prefix matching should be case-insensitive."""
        result = complete_task_type("RESEARCH")
        assert "research" in result
        assert "research_review" in result

    def test_nonmatching_prefix_returns_empty(self) -> None:
        """Non-matching prefix should return empty list."""
        result = complete_task_type("xyz")
        assert result == []

    def test_single_match(self) -> None:
        """Prefix matching only one type returns single result."""
        result = complete_task_type("discover")
        assert result == ["discover"]

    def test_partial_prefix(self) -> None:
        """Partial prefix matches multiple related types."""
        result = complete_task_type("impl")
        assert "implementation" in result
        assert "implementation_review" in result
        assert len(result) == 2

    def test_plan_prefix(self) -> None:
        """Plan prefix matches plan-related types."""
        result = complete_task_type("plan")
        assert "plan_generation" in result
        assert "plan_review" in result
        assert len(result) == 2


@pytest.mark.unit
class TestCompleteExportFormat:
    """Tests for complete_export_format function."""

    def test_empty_prefix_returns_all_formats(self) -> None:
        """Empty prefix should return all available formats."""
        result = complete_export_format("")
        # json and toml are always available
        assert "json" in result
        assert "toml" in result
        # yaml is included if pyyaml is installed
        assert len(result) >= 2

    def test_results_are_sorted(self) -> None:
        """Results should be alphabetically sorted."""
        result = complete_export_format("")
        assert result == sorted(result)

    def test_prefix_filters_results(self) -> None:
        """Prefix should filter to matching formats only."""
        result = complete_export_format("j")
        assert result == ["json"]

    def test_toml_prefix(self) -> None:
        """Toml prefix matches toml format."""
        result = complete_export_format("t")
        assert result == ["toml"]

    def test_prefix_case_insensitive(self) -> None:
        """Prefix matching should be case-insensitive."""
        result = complete_export_format("JSON")
        assert result == ["json"]

    def test_nonmatching_prefix_returns_empty(self) -> None:
        """Non-matching prefix should return empty list."""
        result = complete_export_format("xyz")
        assert result == []

    def test_yaml_available_if_installed(self) -> None:
        """Yaml format is included if pyyaml is available."""
        try:
            import yaml  # noqa: F401

            result = complete_export_format("y")
            assert result == ["yaml"]
        except ImportError:
            # pyyaml not installed, yaml should not be in results
            result = complete_export_format("y")
            assert result == []


@pytest.mark.unit
class TestMarkdownFileCompletion:
    """Tests for complete_markdown_file function.

    Uses tmp_path fixture for real filesystem tests to avoid complex mocking
    issues with Path method interception.
    """

    def test_empty_prefix_returns_md_files_and_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty prefix should return markdown files and directories."""
        # Create test files
        (tmp_path / "docs").mkdir()
        (tmp_path / "README.md").write_text("# README")
        (tmp_path / "script.py").write_text("print('hello')")

        monkeypatch.chdir(tmp_path)
        result = complete_markdown_file("")
        # Should include directory and md file, exclude .py file
        assert "README.md" in result
        assert "docs/" in result
        assert "script.py" not in result

    def test_prefix_filters_results(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Prefix should filter to matching files only."""
        (tmp_path / "plan.md").write_text("# Plan")
        (tmp_path / "spec.md").write_text("# Spec")
        (tmp_path / "plans").mkdir()

        monkeypatch.chdir(tmp_path)
        result = complete_markdown_file("pla")
        # Should match plan.md and plans/, but not spec.md
        assert "plan.md" in result
        assert "plans/" in result
        assert "spec.md" not in result

    def test_prefix_case_insensitive(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Prefix matching should be case-insensitive."""
        (tmp_path / "README.md").write_text("# README")
        (tmp_path / "readme.md").write_text("# readme")

        monkeypatch.chdir(tmp_path)
        result = complete_markdown_file("READ")
        # Should match both README.md and readme.md (case-insensitive)
        assert "README.md" in result
        assert "readme.md" in result

    def test_hidden_files_excluded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Hidden files and directories should be excluded."""
        (tmp_path / ".hidden.md").write_text("# Hidden")
        (tmp_path / ".git").mkdir()
        (tmp_path / "visible.md").write_text("# Visible")

        monkeypatch.chdir(tmp_path)
        result = complete_markdown_file("")
        assert "visible.md" in result
        assert ".hidden.md" not in result
        assert ".git/" not in result

    def test_results_capped_at_20(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Results should be capped at 20 entries."""
        # Create 25 markdown files
        for i in range(25):
            (tmp_path / f"file{i:02d}.md").write_text(f"# File {i}")

        monkeypatch.chdir(tmp_path)
        result = complete_markdown_file("")
        assert len(result) == 20

    def test_results_alphabetically_sorted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Results should be alphabetically sorted."""
        (tmp_path / "zebra.md").write_text("# Zebra")
        (tmp_path / "alpha.md").write_text("# Alpha")
        (tmp_path / "beta").mkdir()

        monkeypatch.chdir(tmp_path)
        result = complete_markdown_file("")
        assert result == ["alpha.md", "beta/", "zebra.md"]

    def test_directory_permission_error_returns_empty(self) -> None:
        """Permission error reading directory should return empty list."""
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "iterdir", side_effect=PermissionError),
        ):
            result = complete_markdown_file("")
            assert result == []

    def test_entry_permission_error_skipped(self) -> None:
        """Permission error on individual entry should skip that entry."""
        good_entry = MagicMock(spec=Path)
        good_entry.name = "good.md"
        good_entry.is_dir.return_value = False
        good_entry.is_file.return_value = True
        good_entry.suffix = ".md"
        good_entry.__str__ = MagicMock(return_value="good.md")

        bad_entry = MagicMock(spec=Path)
        bad_entry.name = "bad.md"
        bad_entry.is_dir.side_effect = PermissionError
        bad_entry.is_file.side_effect = PermissionError

        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "iterdir", return_value=iter([good_entry, bad_entry])),
        ):
            result = complete_markdown_file("")
            assert "good.md" in result
            assert "bad.md" not in result

    def test_nonexistent_directory_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-existent directory should return empty list."""
        monkeypatch.chdir(tmp_path)
        result = complete_markdown_file("nonexistent/")
        assert result == []

    def test_path_with_trailing_slash_lists_directory_contents(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Path ending with / should list contents of that directory."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "plan.md").write_text("# Plan")

        monkeypatch.chdir(tmp_path)
        result = complete_markdown_file("docs/")
        assert "docs/plan.md" in result

    def test_directories_have_trailing_slash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Directories in results should have trailing slash."""
        (tmp_path / "mydir").mkdir()

        monkeypatch.chdir(tmp_path)
        result = complete_markdown_file("")
        assert "mydir/" in result
        assert "mydir" not in result

    def test_only_md_suffix_included(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Only .md files should be included, not other extensions."""
        (tmp_path / "doc.md").write_text("# md")
        (tmp_path / "doc.MD").write_text("# MD")
        (tmp_path / "doc.txt").write_text("txt")
        (tmp_path / "doc.rst").write_text("rst")
        (tmp_path / "doc.markdown").write_text("markdown")

        monkeypatch.chdir(tmp_path)
        result = complete_markdown_file("")
        # .md and .MD should be included (case-insensitive suffix check)
        assert "doc.md" in result
        assert "doc.MD" in result
        # Other extensions should be excluded
        assert "doc.txt" not in result
        assert "doc.rst" not in result
        assert "doc.markdown" not in result

    def test_subdirectory_prefix_filtering(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prefix in subdirectory path should filter correctly."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "plan.md").write_text("# Plan")
        (docs_dir / "spec.md").write_text("# Spec")
        (docs_dir / "planning").mkdir()

        monkeypatch.chdir(tmp_path)
        result = complete_markdown_file("docs/pla")
        # Should match plan.md and planning/, but not spec.md
        assert "docs/plan.md" in result
        assert "docs/planning/" in result
        assert "docs/spec.md" not in result


@pytest.mark.unit
class TestCompleteStepNumber:
    """Tests for complete_step_number function."""

    def test_empty_prefix_returns_all_steps(self) -> None:
        """Empty prefix should return all static step numbers."""
        result = complete_step_number("")
        expected = ["1.1", "1.2", "1.3", "2.1", "2.2", "2.3", "3.1", "3.2", "3.3"]
        assert result == expected

    def test_prefix_filters_by_phase(self) -> None:
        """Prefix should filter to steps in matching phase."""
        result = complete_step_number("1")
        assert result == ["1.1", "1.2", "1.3"]

        result = complete_step_number("2")
        assert result == ["2.1", "2.2", "2.3"]

        result = complete_step_number("3")
        assert result == ["3.1", "3.2", "3.3"]

    def test_prefix_filters_exact_step(self) -> None:
        """Full step prefix should return single match."""
        result = complete_step_number("1.1")
        assert result == ["1.1"]

        result = complete_step_number("2.3")
        assert result == ["2.3"]

    def test_prefix_with_dot_filters_correctly(self) -> None:
        """Prefix with dot should filter to matching steps."""
        result = complete_step_number("1.")
        assert result == ["1.1", "1.2", "1.3"]

        result = complete_step_number("2.")
        assert result == ["2.1", "2.2", "2.3"]

    def test_nonmatching_prefix_returns_empty(self) -> None:
        """Non-matching prefix should return empty list."""
        result = complete_step_number("4")
        assert result == []

        result = complete_step_number("xyz")
        assert result == []

    def test_partial_step_number_filters(self) -> None:
        """Partial step number prefix should filter correctly."""
        result = complete_step_number("1.2")
        assert result == ["1.2"]

        result = complete_step_number("3.1")
        assert result == ["3.1"]


@pytest.mark.unit
class TestCompletePhaseNumber:
    """Tests for complete_phase_number function."""

    def test_empty_prefix_returns_all_phases(self) -> None:
        """Empty prefix should return all static phase numbers."""
        result = complete_phase_number("")
        expected = ["1", "2", "3", "4", "5"]
        assert result == expected

    def test_prefix_filters_results(self) -> None:
        """Prefix should filter to matching phase numbers."""
        result = complete_phase_number("1")
        assert result == ["1"]

        result = complete_phase_number("3")
        assert result == ["3"]

    def test_nonmatching_prefix_returns_empty(self) -> None:
        """Non-matching prefix should return empty list."""
        result = complete_phase_number("6")
        assert result == []

        result = complete_phase_number("xyz")
        assert result == []

    def test_all_phases_matchable(self) -> None:
        """Each phase number should be individually matchable."""
        for phase in ["1", "2", "3", "4", "5"]:
            result = complete_phase_number(phase)
            assert result == [phase]


@pytest.mark.unit
class TestAutoInstallCompletion:
    """Tests for auto-install shell completion functions."""

    def test_get_completion_marker_path_returns_xdg_path(self) -> None:
        """Marker path should be in ~/.local/share/weld/."""
        path = get_completion_marker_path()
        assert path.name == "completion_installed"
        assert "weld" in str(path)
        assert ".local/share" in str(path)

    def test_marker_file_prevents_reinstall(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If marker file exists, auto_install_completion returns early."""
        # Setup fake home directory
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        # Create marker file
        marker_dir = fake_home / ".local" / "share" / "weld"
        marker_dir.mkdir(parents=True)
        (marker_dir / "completion_installed").write_text("bash\n")

        # Should return early without installing
        success, message = auto_install_completion()
        assert success is True
        assert message == ""

    def test_is_completion_installed_false_when_no_marker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """is_completion_installed returns False when marker doesn't exist."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        assert is_completion_installed() is False

    def test_is_completion_installed_true_when_marker_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """is_completion_installed returns True when marker exists."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        marker_dir = fake_home / ".local" / "share" / "weld"
        marker_dir.mkdir(parents=True)
        (marker_dir / "completion_installed").write_text("zsh\n")

        assert is_completion_installed() is True

    def test_mark_completion_installed_creates_marker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """mark_completion_installed creates marker file with shell name."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        mark_completion_installed("zsh")

        marker = fake_home / ".local" / "share" / "weld" / "completion_installed"
        assert marker.exists()
        assert marker.read_text() == "zsh\n"

    def test_mark_completion_installed_creates_parent_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """mark_completion_installed creates parent directories if needed."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        # Parent dirs don't exist yet
        marker_dir = fake_home / ".local" / "share" / "weld"
        assert not marker_dir.exists()

        mark_completion_installed("bash")

        assert marker_dir.exists()
        assert (marker_dir / "completion_installed").exists()

    def test_detect_shell_from_environment_bash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """detect_shell returns bash when SHELL is /bin/bash."""
        monkeypatch.setenv("SHELL", "/bin/bash")
        assert detect_shell() == "bash"

    def test_detect_shell_from_environment_zsh(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """detect_shell returns zsh when SHELL is /usr/bin/zsh."""
        monkeypatch.setenv("SHELL", "/usr/bin/zsh")
        assert detect_shell() == "zsh"

    def test_detect_shell_from_environment_fish(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """detect_shell returns fish when SHELL is /usr/local/bin/fish."""
        monkeypatch.setenv("SHELL", "/usr/local/bin/fish")
        assert detect_shell() == "fish"

    def test_detect_shell_returns_none_for_unsupported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """detect_shell returns None for unsupported shells."""
        monkeypatch.setenv("SHELL", "/bin/tcsh")
        assert detect_shell() is None

    def test_detect_shell_returns_none_when_shell_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """detect_shell returns None when SHELL env var is not set."""
        monkeypatch.delenv("SHELL", raising=False)
        assert detect_shell() is None

    def test_get_rc_file_path_bash(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """_get_rc_file_path returns ~/.bashrc for bash."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        rc_path = _get_rc_file_path("bash")
        assert rc_path == fake_home / ".bashrc"

    def test_get_rc_file_path_zsh(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """_get_rc_file_path returns ~/.zshrc for zsh."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        rc_path = _get_rc_file_path("zsh")
        assert rc_path == fake_home / ".zshrc"

    def test_get_rc_file_path_fish(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """_get_rc_file_path returns fish completions dir for fish."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        rc_path = _get_rc_file_path("fish")
        assert rc_path == fake_home / ".config" / "fish" / "completions" / "weld.fish"

    def test_get_rc_file_path_unsupported_returns_none(self) -> None:
        """_get_rc_file_path returns None for unsupported shells."""
        assert _get_rc_file_path("tcsh") is None
        assert _get_rc_file_path("ksh") is None

    def test_completion_already_in_rc_detects_marker(self, tmp_path: Path) -> None:
        """_completion_already_in_rc returns True if marker comment is present."""
        rc_file = tmp_path / ".bashrc"
        rc_file.write_text(f"# some config\n{_COMPLETION_MARKER}\neval weld\n")

        assert _completion_already_in_rc(rc_file) is True

    def test_completion_already_in_rc_detects_weld_keyword(self, tmp_path: Path) -> None:
        """_completion_already_in_rc returns True if 'weld' is in file."""
        rc_file = tmp_path / ".bashrc"
        rc_file.write_text("# weld completion manually added\neval ...\n")

        assert _completion_already_in_rc(rc_file) is True

    def test_completion_already_in_rc_false_when_not_present(self, tmp_path: Path) -> None:
        """_completion_already_in_rc returns False if weld not configured."""
        rc_file = tmp_path / ".bashrc"
        rc_file.write_text("# some other config\nexport PATH=...\n")

        assert _completion_already_in_rc(rc_file) is False

    def test_completion_already_in_rc_false_when_file_missing(self, tmp_path: Path) -> None:
        """_completion_already_in_rc returns False if file doesn't exist."""
        rc_file = tmp_path / ".bashrc"

        assert _completion_already_in_rc(rc_file) is False

    def test_install_completion_to_rc_appends_for_bash(self, tmp_path: Path) -> None:
        """_install_completion_to_rc appends to bashrc."""
        rc_file = tmp_path / ".bashrc"
        rc_file.write_text("# existing config\n")

        script = 'eval "$(weld --install-completion)"'
        result = _install_completion_to_rc("bash", rc_file, script)

        assert result is True
        content = rc_file.read_text()
        assert "# existing config" in content
        assert _COMPLETION_MARKER in content
        assert script in content

    def test_install_completion_to_rc_creates_fish_file(self, tmp_path: Path) -> None:
        """_install_completion_to_rc creates fish completion file."""
        fish_dir = tmp_path / ".config" / "fish" / "completions"
        fish_file = fish_dir / "weld.fish"

        script = "complete -c weld -a commands"
        result = _install_completion_to_rc("fish", fish_file, script)

        assert result is True
        assert fish_file.exists()
        content = fish_file.read_text()
        assert _COMPLETION_MARKER in content
        assert script in content

    def test_install_failure_doesnt_crash_cli(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """auto_install_completion returns gracefully on failure."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setenv("SHELL", "/bin/bash")

        # Create bashrc but make script generation fail
        (fake_home / ".bashrc").write_text("# config\n")

        with patch("weld.completions._get_completion_script", return_value=None):
            success, message = auto_install_completion()

        # Should fail gracefully
        assert success is False
        assert message == ""

    def test_auto_install_skips_when_shell_unknown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """auto_install_completion skips when shell cannot be detected."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.delenv("SHELL", raising=False)

        success, message = auto_install_completion()

        assert success is False
        assert message == ""

    def test_auto_install_marks_existing_as_installed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """auto_install_completion marks as installed if already in RC file."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setenv("SHELL", "/bin/bash")

        # Create bashrc with existing weld config
        (fake_home / ".bashrc").write_text("# weld completion\n")

        success, message = auto_install_completion()

        # Should succeed silently and create marker
        assert success is True
        assert message == ""
        marker = fake_home / ".local" / "share" / "weld" / "completion_installed"
        assert marker.exists()

    def test_auto_install_creates_marker_on_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """auto_install_completion creates marker file on successful install."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setenv("SHELL", "/bin/bash")

        # Create empty bashrc
        (fake_home / ".bashrc").write_text("")

        # Mock script generation
        mock_script = 'eval "$(weld complete bash)"'
        with patch("weld.completions._get_completion_script", return_value=mock_script):
            success, message = auto_install_completion()

        assert success is True
        assert "source ~/.bashrc" in message

        # Verify marker was created
        marker = fake_home / ".local" / "share" / "weld" / "completion_installed"
        assert marker.exists()
        assert marker.read_text() == "bash\n"

    def test_auto_install_message_for_fish(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """auto_install_completion returns appropriate message for fish."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setenv("SHELL", "/usr/bin/fish")

        mock_script = "complete -c weld -a commands"
        with patch("weld.completions._get_completion_script", return_value=mock_script):
            success, message = auto_install_completion()

        assert success is True
        # Fish doesn't need sourcing - completions are auto-loaded
        assert "Shell completions installed for weld." in message
        assert "source" not in message
