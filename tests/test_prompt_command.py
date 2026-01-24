"""Tests for weld prompt command."""

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from weld.cli import app
from weld.config import TaskType


class TestPromptHelp:
    """Tests for prompt command help and basic invocation."""

    def test_prompt_help(self, runner: CliRunner) -> None:
        """prompt --help should show subcommands."""
        result = runner.invoke(app, ["prompt", "--help"])
        assert result.exit_code == 0
        assert "list" in result.stdout
        assert "show" in result.stdout
        assert "export" in result.stdout

    def test_prompt_list_help(self, runner: CliRunner) -> None:
        """prompt list --help should show usage."""
        result = runner.invoke(app, ["prompt", "list", "--help"])
        assert result.exit_code == 0

    def test_prompt_show_help(self, runner: CliRunner) -> None:
        """prompt show --help should show options."""
        result = runner.invoke(app, ["prompt", "show", "--help"])
        assert result.exit_code == 0
        assert "--raw" in result.stdout
        assert "--focus" in result.stdout

    def test_prompt_export_help(self, runner: CliRunner) -> None:
        """prompt export --help should show options."""
        result = runner.invoke(app, ["prompt", "export", "--help"])
        assert result.exit_code == 0
        assert "--raw" in result.stdout
        assert "--format" in result.stdout


class TestPromptList:
    """Tests for weld prompt list command."""

    def test_prompt_list_not_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """prompt list should fail when not in a git repository."""
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(app, ["prompt", "list"])
            assert result.exit_code == 3
            assert "Not a git repository" in result.stdout
        finally:
            os.chdir(original)

    def test_prompt_list_not_initialized(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """prompt list should fail when weld is not initialized."""
        result = runner.invoke(app, ["prompt", "list"])
        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    def test_prompt_list_shows_all_task_types(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt list should show all task types."""
        result = runner.invoke(app, ["prompt", "list"])
        assert result.exit_code == 0
        # Verify all task types are listed
        for task in TaskType:
            assert task.value in result.stdout

    def test_prompt_list_shows_descriptions(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt list should show descriptions for each task type."""
        result = runner.invoke(app, ["prompt", "list"])
        assert result.exit_code == 0
        # Check some key descriptions appear
        assert "discovery" in result.stdout.lower()
        assert "Implementation" in result.stdout

    def test_prompt_list_shows_customization_status(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt list should indicate customization status."""
        result = runner.invoke(app, ["prompt", "list"])
        assert result.exit_code == 0
        # By default, no customizations configured
        assert "Global customization:" in result.stdout

    def test_prompt_list_json_output(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt list --json should output JSON format."""
        result = runner.invoke(app, ["--json", "prompt", "list"])
        assert result.exit_code == 0
        # Parse JSON output - wrapped in schema
        output = json.loads(result.stdout)
        assert "data" in output
        data = output["data"]
        assert "tasks" in data
        assert isinstance(data["tasks"], list)
        # Should have entry for each TaskType
        assert len(data["tasks"]) == len(TaskType)

    def test_prompt_list_json_has_task_details(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt list --json should include task details."""
        result = runner.invoke(app, ["--json", "prompt", "list"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        data = output["data"]
        # Each task entry should have expected fields
        for task in data["tasks"]:
            assert "name" in task
            assert "description" in task
            assert "customized" in task

    def test_prompt_list_with_customization(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt list should show configured customizations."""
        # Update config with customization
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts]
global_prefix = "Focus on security"

[prompts.research]
prefix = "Research with extra detail"
"""
        config_file.write_text(config_content)

        result = runner.invoke(app, ["prompt", "list"])
        assert result.exit_code == 0
        # Global customization should be shown
        assert "configured" in result.stdout.lower()

    def test_prompt_default_invocation_shows_list(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """weld prompt without subcommand should show list."""
        result = runner.invoke(app, ["prompt"])
        assert result.exit_code == 0
        # Should show same output as list
        for task in TaskType:
            assert task.value in result.stdout


class TestPromptShow:
    """Tests for weld prompt show command."""

    def test_prompt_show_not_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """prompt show should fail when not in a git repository."""
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(app, ["prompt", "show", "discover"])
            assert result.exit_code == 3
            assert "Not a git repository" in result.stdout
        finally:
            os.chdir(original)

    def test_prompt_show_not_initialized(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """prompt show should fail when weld is not initialized."""
        result = runner.invoke(app, ["prompt", "show", "discover"])
        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    def test_prompt_show_invalid_task_type(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt show should fail for invalid task type."""
        result = runner.invoke(app, ["prompt", "show", "invalid_type"])
        assert result.exit_code == 1
        assert "Invalid task type" in result.stdout

    def test_prompt_show_valid_task_type(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt show should display customization for valid task type."""
        result = runner.invoke(app, ["prompt", "show", "discover"])
        assert result.exit_code == 0
        assert "discover" in result.stdout
        assert "prefix" in result.stdout.lower()
        assert "suffix" in result.stdout.lower()

    def test_prompt_show_all_task_types(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt show should work for all valid task types."""
        for task in TaskType:
            result = runner.invoke(app, ["prompt", "show", task.value])
            assert result.exit_code == 0, f"Failed for task type: {task.value}"

    def test_prompt_show_raw_output(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt show --raw should output raw template."""
        result = runner.invoke(app, ["prompt", "show", "discover", "--raw"])
        assert result.exit_code == 0
        # Raw output should contain template structure
        assert "Base Template" in result.stdout

    def test_prompt_show_raw_with_focus(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt show --raw --focus should substitute focus value."""
        result = runner.invoke(
            app, ["prompt", "show", "discover", "--raw", "--focus", "security analysis"]
        )
        assert result.exit_code == 0
        assert "security analysis" in result.stdout

    def test_prompt_show_json_output(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt show --json should output JSON format."""
        result = runner.invoke(app, ["--json", "prompt", "show", "discover"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert "data" in output
        data = output["data"]
        assert "task" in data
        assert data["task"] == "discover"
        assert "prefix" in data
        assert "suffix" in data

    def test_prompt_show_with_focus_option(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt show --focus should show effective focus value."""
        result = runner.invoke(app, ["prompt", "show", "discover", "--focus", "API security"])
        assert result.exit_code == 0
        assert "API security" in result.stdout

    def test_prompt_show_displays_global_config(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt show should display global prefix/suffix configuration."""
        # Add global config
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts]
global_prefix = "Global prefix text"
global_suffix = "Global suffix text"
"""
        config_file.write_text(config_content)

        result = runner.invoke(app, ["prompt", "show", "discover"])
        assert result.exit_code == 0
        assert "Global prefix text" in result.stdout
        assert "Global suffix text" in result.stdout

    def test_prompt_show_displays_task_config(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt show should display task-specific configuration."""
        # Add task-specific config
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts.research]
prefix = "Research prefix"
suffix = "Research suffix"
default_focus = "security"
"""
        config_file.write_text(config_content)

        result = runner.invoke(app, ["prompt", "show", "research"])
        assert result.exit_code == 0
        assert "Research prefix" in result.stdout
        assert "Research suffix" in result.stdout
        assert "security" in result.stdout

    def test_prompt_show_raw_includes_customizations(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt show --raw should include customizations in output."""
        # Add customizations
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts]
global_prefix = "Global prefix"

[prompts.research]
prefix = "Task prefix"
"""
        config_file.write_text(config_content)

        result = runner.invoke(app, ["prompt", "show", "research", "--raw"])
        assert result.exit_code == 0
        assert "Global Prefix" in result.stdout
        assert "Task Prefix" in result.stdout

    def test_prompt_show_raw_not_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """prompt show --raw should show plain error when not in git repo."""
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(app, ["prompt", "show", "discover", "--raw"])
            assert result.exit_code == 3
            assert "Not a git repository" in result.stdout
        finally:
            os.chdir(original)

    def test_prompt_show_raw_invalid_task_type(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt show --raw with invalid task type should show plain error."""
        result = runner.invoke(app, ["prompt", "show", "invalid", "--raw"])
        assert result.exit_code == 1
        assert "Invalid task type" in result.stdout


class TestPromptExport:
    """Tests for weld prompt export command."""

    def test_prompt_export_not_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """prompt export should fail when not in a git repository."""
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(app, ["prompt", "export"])
            assert result.exit_code == 3
            assert "Not a git repository" in result.stdout
        finally:
            os.chdir(original)

    def test_prompt_export_not_initialized(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """prompt export should fail when weld is not initialized."""
        result = runner.invoke(app, ["prompt", "export"])
        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    def test_prompt_export_toml_to_stdout(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt export without path should output TOML to stdout."""
        result = runner.invoke(app, ["prompt", "export"])
        assert result.exit_code == 0
        # Output should be valid TOML (contains [prompts] section or be empty)
        assert "prompts" in result.stdout or result.stdout.strip() == ""

    def test_prompt_export_json_format(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt export --format json should output JSON."""
        result = runner.invoke(app, ["prompt", "export", "--format", "json"])
        assert result.exit_code == 0
        # Should be valid JSON
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_prompt_export_invalid_format(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt export with invalid format should fail."""
        result = runner.invoke(app, ["prompt", "export", "--format", "yaml"])
        assert result.exit_code == 1
        assert "Invalid format" in result.stdout

    def test_prompt_export_to_file(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt export --output should write to file."""
        output_file = initialized_weld / "prompts.toml"
        result = runner.invoke(app, ["prompt", "export", "--output", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()

    def test_prompt_export_to_directory(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt export <path> should write config to file."""
        # The directory argument is treated as a file path for non-raw mode
        output_file = initialized_weld / "prompts.toml"
        result = runner.invoke(app, ["prompt", "export", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()

    def test_prompt_export_json_to_file(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt export --format json --output should write JSON to file."""
        output_file = initialized_weld / "prompts.json"
        result = runner.invoke(
            app, ["prompt", "export", "--format", "json", "--output", str(output_file)]
        )
        assert result.exit_code == 0
        assert output_file.exists()
        # Verify it's valid JSON
        data = json.loads(output_file.read_text())
        assert isinstance(data, dict)

    def test_prompt_export_raw_mode(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt export <dir> --raw should export templates as markdown files."""
        export_dir = initialized_weld / "prompts_export"
        result = runner.invoke(app, ["prompt", "export", str(export_dir), "--raw"])
        assert result.exit_code == 0
        assert export_dir.exists()
        # Should have a markdown file for each task type
        for task in TaskType:
            md_file = export_dir / f"{task.value}.md"
            assert md_file.exists(), f"Missing export file for {task.value}"

    def test_prompt_export_raw_requires_directory(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt export --raw without directory should fail."""
        result = runner.invoke(app, ["prompt", "export", "--raw"])
        assert result.exit_code == 1
        assert "Directory argument required" in result.stdout

    def test_prompt_export_raw_creates_directory(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt export --raw should create directory if it doesn't exist."""
        export_dir = initialized_weld / "new_dir" / "nested"
        assert not export_dir.exists()
        result = runner.invoke(app, ["prompt", "export", str(export_dir), "--raw"])
        assert result.exit_code == 0
        assert export_dir.exists()

    def test_prompt_export_raw_content(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt export --raw should include template content."""
        export_dir = initialized_weld / "prompts_export"
        result = runner.invoke(app, ["prompt", "export", str(export_dir), "--raw"])
        assert result.exit_code == 0

        # Check discover.md has expected structure
        discover_file = export_dir / "discover.md"
        content = discover_file.read_text()
        assert "# discover" in content
        assert "Base Template" in content

    def test_prompt_export_raw_includes_customizations(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt export --raw should include configured customizations."""
        # Add customizations
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts]
global_prefix = "Global prefix for all"

[prompts.discover]
prefix = "Discover-specific prefix"
default_focus = "architecture"
"""
        config_file.write_text(config_content)

        export_dir = initialized_weld / "prompts_export"
        result = runner.invoke(app, ["prompt", "export", str(export_dir), "--raw"])
        assert result.exit_code == 0

        # Check customizations are included
        discover_file = export_dir / "discover.md"
        content = discover_file.read_text()
        assert "Global Prefix" in content
        assert "Global prefix for all" in content
        assert "Task Prefix" in content
        assert "Discover-specific prefix" in content

    def test_prompt_export_dry_run(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt export --dry-run should not create files."""
        export_dir = initialized_weld / "prompts_export"
        result = runner.invoke(app, ["--dry-run", "prompt", "export", str(export_dir), "--raw"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert not export_dir.exists()

    def test_prompt_export_dry_run_config(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt export --dry-run for config should show what would be written."""
        output_file = initialized_weld / "prompts.toml"
        result = runner.invoke(app, ["--dry-run", "prompt", "export", str(output_file)])
        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert not output_file.exists()

    def test_prompt_export_raw_json_mode(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt export --raw --json should output JSON summary."""
        export_dir = initialized_weld / "prompts_export"
        result = runner.invoke(app, ["--json", "prompt", "export", str(export_dir), "--raw"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert "data" in output
        data = output["data"]
        assert "directory" in data
        assert "count" in data
        assert data["count"] == len(TaskType)

    def test_prompt_export_includes_customized_values(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt export should include configured customization values."""
        # Add customizations
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts]
global_prefix = "Python 3.12 project"

[prompts.research]
prefix = "Security focus"
default_focus = "security"
"""
        config_file.write_text(config_content)

        result = runner.invoke(app, ["prompt", "export", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "global_prefix" in data
        assert data["global_prefix"] == "Python 3.12 project"
        assert "research" in data
        assert data["research"]["prefix"] == "Security focus"


class TestPromptEdgeCases:
    """Edge case tests for prompt commands."""

    def test_prompt_show_default_focus_used(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt show should use default_focus when --focus not provided."""
        # Add default_focus
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts.discover]
default_focus = "performance optimization"
"""
        config_file.write_text(config_content)

        result = runner.invoke(app, ["prompt", "show", "discover"])
        assert result.exit_code == 0
        assert "performance optimization" in result.stdout

    def test_prompt_show_explicit_focus_overrides_default(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt show --focus should override configured default_focus."""
        # Add default_focus
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts.discover]
default_focus = "performance optimization"
"""
        config_file.write_text(config_content)

        result = runner.invoke(app, ["prompt", "show", "discover", "--focus", "security audit"])
        assert result.exit_code == 0
        assert "security audit" in result.stdout

    def test_prompt_list_truncates_long_values(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt list should truncate long prefix/suffix values in display."""
        # Add very long prefix
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        long_prefix = "A" * 200
        config_content += f"""
[prompts]
global_prefix = "{long_prefix}"
"""
        config_file.write_text(config_content)

        result = runner.invoke(app, ["prompt", "list"])
        assert result.exit_code == 0
        # Full 200-char string should not appear
        assert long_prefix not in result.stdout
        # But should show truncated version with ellipsis
        assert "..." in result.stdout

    def test_prompt_commands_with_unicode(self, runner: CliRunner, initialized_weld: Path) -> None:
        """prompt commands should handle unicode in configuration."""
        # Add unicode content
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts]
global_prefix = "Focus on: security \u2714, performance \u2714"
"""
        config_file.write_text(config_content)

        result = runner.invoke(app, ["prompt", "list"])
        assert result.exit_code == 0
        # Should handle unicode gracefully

    def test_prompt_export_empty_customizations(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt export should handle empty customizations gracefully."""
        result = runner.invoke(app, ["prompt", "export", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        # With no customizations, should be empty dict
        assert isinstance(data, dict)

    def test_prompt_show_unconfigured_task_shows_none(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """prompt show for unconfigured task should show (none) for values."""
        result = runner.invoke(app, ["prompt", "show", "fix_generation"])
        assert result.exit_code == 0
        assert "(none)" in result.stdout
