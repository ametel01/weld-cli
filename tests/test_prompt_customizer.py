"""Tests for prompt customizer module."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from weld.cli import app
from weld.config import (
    PromptCustomization,
    PromptsConfig,
    TaskType,
    WeldConfig,
)
from weld.core.prompt_customizer import apply_customization, get_default_focus


class TestApplyCustomization:
    """Tests for apply_customization function."""

    def test_no_customization_returns_original_prompt(self) -> None:
        """When no customization is configured, return prompt unchanged."""
        config = PromptsConfig()
        prompt = "Analyze the codebase"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        assert result == prompt

    def test_global_prefix_only(self) -> None:
        """Global prefix is prepended to the prompt."""
        config = PromptsConfig(global_prefix="This is a Python project.")
        prompt = "Analyze the codebase"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        assert result == "This is a Python project.\n\nAnalyze the codebase"

    def test_global_suffix_only(self) -> None:
        """Global suffix is appended to the prompt."""
        config = PromptsConfig(global_suffix="Follow PEP 8 conventions.")
        prompt = "Analyze the codebase"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        assert result == "Analyze the codebase\n\nFollow PEP 8 conventions."

    def test_global_prefix_and_suffix(self) -> None:
        """Global prefix and suffix wrap the prompt."""
        config = PromptsConfig(
            global_prefix="This is a Python project.",
            global_suffix="Follow PEP 8 conventions.",
        )
        prompt = "Analyze the codebase"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        expected = "This is a Python project.\n\nAnalyze the codebase\n\nFollow PEP 8 conventions."
        assert result == expected

    def test_task_prefix_only(self) -> None:
        """Task-specific prefix is prepended to the prompt."""
        config = PromptsConfig(discover=PromptCustomization(prefix="Focus on architecture."))
        prompt = "Analyze the codebase"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        assert result == "Focus on architecture.\n\nAnalyze the codebase"

    def test_task_suffix_only(self) -> None:
        """Task-specific suffix is appended to the prompt."""
        config = PromptsConfig(discover=PromptCustomization(suffix="Include dependency analysis."))
        prompt = "Analyze the codebase"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        assert result == "Analyze the codebase\n\nInclude dependency analysis."

    def test_task_prefix_and_suffix(self) -> None:
        """Task-specific prefix and suffix wrap the prompt."""
        config = PromptsConfig(
            discover=PromptCustomization(
                prefix="Focus on architecture.",
                suffix="Include dependency analysis.",
            )
        )
        prompt = "Analyze the codebase"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        expected = "Focus on architecture.\n\nAnalyze the codebase\n\nInclude dependency analysis."
        assert result == expected

    def test_combined_global_and_task_customization(self) -> None:
        """Combined global and task-specific customization in correct order."""
        config = PromptsConfig(
            global_prefix="This is a Python project.",
            global_suffix="Follow PEP 8 conventions.",
            discover=PromptCustomization(
                prefix="Focus on architecture.",
                suffix="Include dependency analysis.",
            ),
        )
        prompt = "Analyze the codebase"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        # Order: global_prefix → task_prefix → prompt → task_suffix → global_suffix
        expected = (
            "This is a Python project.\n\n"
            "Focus on architecture.\n\n"
            "Analyze the codebase\n\n"
            "Include dependency analysis.\n\n"
            "Follow PEP 8 conventions."
        )
        assert result == expected

    def test_global_prefix_with_task_suffix(self) -> None:
        """Global prefix combined with task-specific suffix."""
        config = PromptsConfig(
            global_prefix="This is a Python project.",
            research=PromptCustomization(suffix="Focus on security."),
        )
        prompt = "Investigate authentication"

        result = apply_customization(prompt, TaskType.RESEARCH, config)

        expected = "This is a Python project.\n\nInvestigate authentication\n\nFocus on security."
        assert result == expected

    def test_task_prefix_with_global_suffix(self) -> None:
        """Task-specific prefix combined with global suffix."""
        config = PromptsConfig(
            global_suffix="Include type hints.",
            plan_generation=PromptCustomization(prefix="Break into small steps."),
        )
        prompt = "Create implementation plan"

        result = apply_customization(prompt, TaskType.PLAN_GENERATION, config)

        expected = "Break into small steps.\n\nCreate implementation plan\n\nInclude type hints."
        assert result == expected

    def test_accepts_weld_config(self) -> None:
        """apply_customization accepts WeldConfig and extracts prompts."""
        weld_config = WeldConfig(
            prompts=PromptsConfig(
                global_prefix="Python 3.12 project.",
                research=PromptCustomization(prefix="Security focus."),
            )
        )
        prompt = "Analyze authentication"

        result = apply_customization(prompt, TaskType.RESEARCH, weld_config)

        expected = "Python 3.12 project.\n\nSecurity focus.\n\nAnalyze authentication"
        assert result == expected

    def test_accepts_task_as_string(self) -> None:
        """apply_customization accepts task type as string."""
        config = PromptsConfig(discover=PromptCustomization(prefix="Focus on structure."))
        prompt = "Analyze the codebase"

        result = apply_customization(prompt, "discover", config)

        assert result == "Focus on structure.\n\nAnalyze the codebase"

    def test_accepts_task_as_enum(self) -> None:
        """apply_customization accepts task type as TaskType enum."""
        config = PromptsConfig(discover=PromptCustomization(prefix="Focus on structure."))
        prompt = "Analyze the codebase"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        assert result == "Focus on structure.\n\nAnalyze the codebase"

    def test_empty_string_prefix_not_applied(self) -> None:
        """Empty string prefix should not be included."""
        config = PromptsConfig(global_prefix="")
        prompt = "Analyze the codebase"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        # Empty string is falsy, so prefix should not be applied
        assert result == prompt

    def test_empty_string_suffix_not_applied(self) -> None:
        """Empty string suffix should not be included."""
        config = PromptsConfig(global_suffix="")
        prompt = "Analyze the codebase"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        # Empty string is falsy, so suffix should not be applied
        assert result == prompt

    def test_empty_string_task_prefix_not_applied(self) -> None:
        """Empty string task prefix should not be included."""
        config = PromptsConfig(discover=PromptCustomization(prefix=""))
        prompt = "Analyze the codebase"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        assert result == prompt

    def test_empty_string_task_suffix_not_applied(self) -> None:
        """Empty string task suffix should not be included."""
        config = PromptsConfig(discover=PromptCustomization(suffix=""))
        prompt = "Analyze the codebase"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        assert result == prompt

    def test_all_task_types_supported(self) -> None:
        """All TaskType values should work with apply_customization."""
        config = PromptsConfig(global_prefix="Test context")
        prompt = "Test prompt"

        for task_type in TaskType:
            result = apply_customization(prompt, task_type, config)
            assert "Test context" in result
            assert "Test prompt" in result

    def test_different_tasks_get_different_customizations(self) -> None:
        """Different task types should get their respective customizations."""
        config = PromptsConfig(
            discover=PromptCustomization(prefix="Discover context"),
            research=PromptCustomization(prefix="Research context"),
            plan_generation=PromptCustomization(prefix="Plan context"),
        )
        prompt = "Base prompt"

        discover_result = apply_customization(prompt, TaskType.DISCOVER, config)
        research_result = apply_customization(prompt, TaskType.RESEARCH, config)
        plan_result = apply_customization(prompt, TaskType.PLAN_GENERATION, config)
        impl_result = apply_customization(prompt, TaskType.IMPLEMENTATION, config)

        assert "Discover context" in discover_result
        assert "Research context" in research_result
        assert "Plan context" in plan_result
        # Implementation has no custom prefix, so only prompt
        assert impl_result == prompt

    def test_multiline_prompt_preserved(self) -> None:
        """Multiline prompts should be preserved correctly."""
        config = PromptsConfig(global_prefix="Context")
        prompt = "Line 1\nLine 2\nLine 3"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        assert result == "Context\n\nLine 1\nLine 2\nLine 3"

    def test_multiline_prefix_preserved(self) -> None:
        """Multiline prefix should be preserved correctly."""
        config = PromptsConfig(global_prefix="Context line 1\nContext line 2")
        prompt = "Analyze"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        assert result == "Context line 1\nContext line 2\n\nAnalyze"


class TestGetDefaultFocus:
    """Tests for get_default_focus function."""

    def test_explicit_focus_takes_precedence(self) -> None:
        """Explicit focus should override configured default."""
        config = PromptsConfig(research=PromptCustomization(default_focus="security"))

        result = get_default_focus(TaskType.RESEARCH, config, explicit_focus="performance")

        assert result == "performance"

    def test_returns_configured_default_when_no_explicit(self) -> None:
        """Return configured default_focus when explicit is not provided."""
        config = PromptsConfig(research=PromptCustomization(default_focus="security"))

        result = get_default_focus(TaskType.RESEARCH, config)

        assert result == "security"

    def test_returns_none_when_no_default_and_no_explicit(self) -> None:
        """Return None when neither default nor explicit focus is set."""
        config = PromptsConfig()

        result = get_default_focus(TaskType.RESEARCH, config)

        assert result is None

    def test_empty_string_explicit_uses_default(self) -> None:
        """Empty string explicit focus should fall back to default."""
        config = PromptsConfig(research=PromptCustomization(default_focus="security"))

        result = get_default_focus(TaskType.RESEARCH, config, explicit_focus="")

        # Empty string is falsy, so falls back to default
        assert result == "security"

    def test_none_explicit_uses_default(self) -> None:
        """None explicit focus should use default."""
        config = PromptsConfig(discover=PromptCustomization(default_focus="architecture"))

        result = get_default_focus(TaskType.DISCOVER, config, explicit_focus=None)

        assert result == "architecture"

    def test_accepts_weld_config(self) -> None:
        """get_default_focus accepts WeldConfig and extracts prompts."""
        weld_config = WeldConfig(
            prompts=PromptsConfig(discover=PromptCustomization(default_focus="structure"))
        )

        result = get_default_focus(TaskType.DISCOVER, weld_config)

        assert result == "structure"

    def test_accepts_task_as_string(self) -> None:
        """get_default_focus accepts task type as string."""
        config = PromptsConfig(discover=PromptCustomization(default_focus="architecture"))

        result = get_default_focus("discover", config)

        assert result == "architecture"

    def test_accepts_task_as_enum(self) -> None:
        """get_default_focus accepts task type as TaskType enum."""
        config = PromptsConfig(discover=PromptCustomization(default_focus="architecture"))

        result = get_default_focus(TaskType.DISCOVER, config)

        assert result == "architecture"

    def test_all_task_types_supported(self) -> None:
        """All TaskType values should work with get_default_focus."""
        config = PromptsConfig()

        for task_type in TaskType:
            # Should not raise, may return None
            result = get_default_focus(task_type, config)
            assert result is None  # No defaults configured

    def test_different_tasks_get_different_defaults(self) -> None:
        """Different task types should get their respective default_focus."""
        config = PromptsConfig(
            discover=PromptCustomization(default_focus="architecture"),
            research=PromptCustomization(default_focus="security"),
            plan_generation=PromptCustomization(default_focus="testability"),
        )

        assert get_default_focus(TaskType.DISCOVER, config) == "architecture"
        assert get_default_focus(TaskType.RESEARCH, config) == "security"
        assert get_default_focus(TaskType.PLAN_GENERATION, config) == "testability"
        # Implementation has no default configured
        assert get_default_focus(TaskType.IMPLEMENTATION, config) is None

    def test_weld_config_with_explicit_override(self) -> None:
        """WeldConfig default focus can be overridden with explicit."""
        weld_config = WeldConfig(
            prompts=PromptsConfig(research=PromptCustomization(default_focus="security"))
        )

        result = get_default_focus(TaskType.RESEARCH, weld_config, explicit_focus="performance")

        assert result == "performance"


class TestIsolation:
    """Tests for configuration isolation between different configs."""

    def test_prompts_config_instances_isolated(self) -> None:
        """Different PromptsConfig instances should not share state."""
        config1 = PromptsConfig(discover=PromptCustomization(prefix="Config 1 prefix"))
        config2 = PromptsConfig(discover=PromptCustomization(prefix="Config 2 prefix"))
        prompt = "Test prompt"

        result1 = apply_customization(prompt, TaskType.DISCOVER, config1)
        result2 = apply_customization(prompt, TaskType.DISCOVER, config2)

        assert "Config 1 prefix" in result1
        assert "Config 2 prefix" in result2
        assert "Config 2 prefix" not in result1
        assert "Config 1 prefix" not in result2

    def test_weld_config_instances_isolated(self) -> None:
        """Different WeldConfig instances should not share prompt state."""
        config1 = WeldConfig(prompts=PromptsConfig(global_prefix="Project A"))
        config2 = WeldConfig(prompts=PromptsConfig(global_prefix="Project B"))
        prompt = "Test prompt"

        result1 = apply_customization(prompt, TaskType.DISCOVER, config1)
        result2 = apply_customization(prompt, TaskType.DISCOVER, config2)

        assert "Project A" in result1
        assert "Project B" in result2
        assert "Project B" not in result1
        assert "Project A" not in result2

    def test_default_focus_isolated_between_tasks(self) -> None:
        """Default focus for one task should not affect another."""
        config = PromptsConfig(research=PromptCustomization(default_focus="security"))

        research_focus = get_default_focus(TaskType.RESEARCH, config)
        discover_focus = get_default_focus(TaskType.DISCOVER, config)

        assert research_focus == "security"
        assert discover_focus is None


class TestEdgeCases:
    """Tests for edge cases and unusual inputs."""

    def test_whitespace_only_prefix_applied(self) -> None:
        """Whitespace-only prefix should be applied (truthy string)."""
        config = PromptsConfig(global_prefix="   ")
        prompt = "Test"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        # Whitespace string is truthy, so it gets applied
        assert result == "   \n\nTest"

    def test_whitespace_only_suffix_applied(self) -> None:
        """Whitespace-only suffix should be applied (truthy string)."""
        config = PromptsConfig(global_suffix="   ")
        prompt = "Test"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        # Whitespace string is truthy, so it gets applied
        assert result == "Test\n\n   "

    def test_whitespace_only_explicit_focus_used(self) -> None:
        """Whitespace-only explicit focus should be used (truthy)."""
        config = PromptsConfig(research=PromptCustomization(default_focus="security"))

        result = get_default_focus(TaskType.RESEARCH, config, explicit_focus="   ")

        # Whitespace is truthy, so explicit takes precedence
        assert result == "   "

    def test_very_long_prompt(self) -> None:
        """Very long prompts should be handled correctly."""
        config = PromptsConfig(global_prefix="Prefix", global_suffix="Suffix")
        long_prompt = "A" * 100000  # 100k characters

        result = apply_customization(long_prompt, TaskType.DISCOVER, config)

        assert result.startswith("Prefix\n\n")
        assert result.endswith("\n\nSuffix")
        assert "A" * 100000 in result

    def test_unicode_in_customization(self) -> None:
        """Unicode characters in customization should work correctly."""
        config = PromptsConfig(
            global_prefix="这是一个Python项目。",
            discover=PromptCustomization(prefix="🔍 分析代码结构"),
        )
        prompt = "Analyze"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        assert "这是一个Python项目。" in result
        assert "🔍 分析代码结构" in result

    def test_newlines_in_prefix_suffix(self) -> None:
        """Newlines within prefix/suffix should be preserved."""
        config = PromptsConfig(
            global_prefix="Line 1\n\nLine 2",
            global_suffix="End 1\n\nEnd 2",
        )
        prompt = "Middle"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        expected = "Line 1\n\nLine 2\n\nMiddle\n\nEnd 1\n\nEnd 2"
        assert result == expected

    def test_special_characters_preserved(self) -> None:
        """Special characters in prompt should be preserved."""
        config = PromptsConfig(global_prefix="Context")
        prompt = "Handle $ and ` and \\ and ' and \" correctly"

        result = apply_customization(prompt, TaskType.DISCOVER, config)

        assert "$ and ` and \\ and ' and \"" in result

    def test_invalid_task_string_raises_error(self) -> None:
        """Invalid task string should raise ValueError."""
        config = PromptsConfig()
        prompt = "Test"

        with pytest.raises(ValueError):
            apply_customization(prompt, "invalid_task", config)

    def test_get_default_focus_invalid_task_raises_error(self) -> None:
        """Invalid task string in get_default_focus should raise ValueError."""
        config = PromptsConfig()

        with pytest.raises(ValueError):
            get_default_focus("invalid_task", config)


@pytest.mark.integration
class TestIntegrationWithMockedCommands:
    """Integration tests verifying customizations are applied when commands run.

    These tests verify that the prompt customization system correctly integrates
    with the command layer - ensuring that when commands like `discover`, `research`,
    or `plan` run, they properly apply configured customizations to their prompts.
    """

    def test_discover_applies_global_prefix(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """discover command should apply global_prefix to generated prompt."""
        # Configure global prefix
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts]
global_prefix = "This is a Python 3.12 monorepo."
"""
        config_file.write_text(config_content)

        # Run in dry-run mode to see the prompt
        result = runner.invoke(app, ["--dry-run", "discover"])

        # In dry-run mode, we should see the customized prompt
        assert result.exit_code == 0
        assert "This is a Python 3.12 monorepo" in result.stdout

    def test_discover_applies_task_prefix(self, runner: CliRunner, initialized_weld: Path) -> None:
        """discover command should apply task-specific prefix."""
        # Configure task-specific prefix
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts.discover]
prefix = "Focus on security architecture patterns."
"""
        config_file.write_text(config_content)

        # Run in dry-run mode
        result = runner.invoke(app, ["--dry-run", "discover"])

        assert result.exit_code == 0
        assert "Focus on security architecture patterns" in result.stdout

    def test_discover_applies_combined_customization(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """discover command should apply both global and task-specific customizations."""
        # Configure both global and task-specific
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts]
global_prefix = "This is a Python CLI project."
global_suffix = "Always consider testability."

[prompts.discover]
prefix = "Focus on the command layer."
suffix = "Note any CLI patterns."
"""
        config_file.write_text(config_content)

        result = runner.invoke(app, ["--dry-run", "discover"])

        assert result.exit_code == 0
        # Verify layered order: global_prefix → task_prefix → prompt → task_suffix → global_suffix
        output = result.stdout
        assert "This is a Python CLI project" in output
        assert "Focus on the command layer" in output
        assert "Note any CLI patterns" in output
        assert "Always consider testability" in output

    def test_discover_uses_default_focus_from_config(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """discover command should use default_focus when --focus not provided."""
        # Configure default_focus
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts.discover]
default_focus = "API layer and authentication patterns"
"""
        config_file.write_text(config_content)

        result = runner.invoke(app, ["--dry-run", "discover"])

        assert result.exit_code == 0
        assert "API layer and authentication patterns" in result.stdout

    def test_discover_explicit_focus_overrides_default(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """discover --focus should override configured default_focus."""
        # Configure default_focus
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts.discover]
default_focus = "API layer patterns"
"""
        config_file.write_text(config_content)

        result = runner.invoke(app, ["--dry-run", "discover", "--focus", "database schema"])

        assert result.exit_code == 0
        assert "database schema" in result.stdout
        # Default focus should not appear when explicit is provided
        assert "API layer patterns" not in result.stdout

    def test_research_applies_global_prefix(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """research command should apply global_prefix to generated prompt."""
        # Configure global prefix
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts]
global_prefix = "This is a security-focused project."
"""
        config_file.write_text(config_content)

        # Create a research topic file
        topic_file = initialized_weld / "topic.md"
        topic_file.write_text("# Research Topic\n\nInvestigate caching strategies.")

        result = runner.invoke(app, ["--dry-run", "research", str(topic_file)])

        assert result.exit_code == 0
        assert "This is a security-focused project" in result.stdout

    def test_research_applies_task_customization(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """research command should apply task-specific customization."""
        # Configure task-specific customization
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts.research]
prefix = "Consider performance implications."
suffix = "Include benchmark recommendations."
"""
        config_file.write_text(config_content)

        topic_file = initialized_weld / "topic.md"
        topic_file.write_text("# Research\n\nDatabase optimization.")

        result = runner.invoke(app, ["--dry-run", "research", str(topic_file)])

        assert result.exit_code == 0
        assert "Consider performance implications" in result.stdout
        assert "Include benchmark recommendations" in result.stdout

    def test_research_uses_default_focus(self, runner: CliRunner, initialized_weld: Path) -> None:
        """research command should use default_focus when --focus not provided."""
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts.research]
default_focus = "security vulnerabilities"
"""
        config_file.write_text(config_content)

        topic_file = initialized_weld / "topic.md"
        topic_file.write_text("# Topic\n\nAuth system.")

        result = runner.invoke(app, ["--dry-run", "research", str(topic_file)])

        assert result.exit_code == 0
        assert "security vulnerabilities" in result.stdout

    def test_plan_applies_global_prefix(self, runner: CliRunner, initialized_weld: Path) -> None:
        """plan command should apply global_prefix to generated prompt."""
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts]
global_prefix = "Follow TDD practices."
"""
        config_file.write_text(config_content)

        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# Feature Spec\n\nAdd user authentication.")

        result = runner.invoke(app, ["--dry-run", "plan", str(spec_file)])

        assert result.exit_code == 0
        assert "Follow TDD practices" in result.stdout

    def test_plan_applies_task_customization(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """plan command should apply task-specific customization."""
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts.plan_generation]
prefix = "Break into small, testable steps."
suffix = "Include rollback strategy."
"""
        config_file.write_text(config_content)

        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# Spec\n\nAdd logging.")

        result = runner.invoke(app, ["--dry-run", "plan", str(spec_file)])

        assert result.exit_code == 0
        assert "Break into small, testable steps" in result.stdout
        assert "Include rollback strategy" in result.stdout

    def test_config_isolation_between_commands(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """Different commands should get their respective task customizations."""
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts]
global_prefix = "Shared context for all."

[prompts.discover]
prefix = "Discover-specific context."

[prompts.research]
prefix = "Research-specific context."

[prompts.plan_generation]
prefix = "Plan-specific context."
"""
        config_file.write_text(config_content)

        # Test discover gets its customization
        discover_result = runner.invoke(app, ["--dry-run", "discover"])
        assert "Shared context for all" in discover_result.stdout
        assert "Discover-specific context" in discover_result.stdout
        assert "Research-specific context" not in discover_result.stdout

        # Test research gets its customization
        topic_file = initialized_weld / "topic.md"
        topic_file.write_text("# Topic\n\nContent.")
        research_result = runner.invoke(app, ["--dry-run", "research", str(topic_file)])
        assert "Shared context for all" in research_result.stdout
        assert "Research-specific context" in research_result.stdout
        assert "Discover-specific context" not in research_result.stdout

        # Test plan gets its customization
        spec_file = initialized_weld / "spec.md"
        spec_file.write_text("# Spec\n\nFeature.")
        plan_result = runner.invoke(app, ["--dry-run", "plan", str(spec_file)])
        assert "Shared context for all" in plan_result.stdout
        assert "Plan-specific context" in plan_result.stdout
        assert "Discover-specific context" not in plan_result.stdout

    def test_unicode_customization_applied(self, runner: CliRunner, initialized_weld: Path) -> None:
        """Unicode characters in customization should be applied correctly."""
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += """
[prompts]
global_prefix = "Project type: Python CLI"
"""
        config_file.write_text(config_content)

        result = runner.invoke(app, ["--dry-run", "discover"])

        assert result.exit_code == 0
        # Unicode should be preserved
        assert "Python CLI" in result.stdout

    def test_multiline_customization_applied(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """Multiline customizations should be applied correctly."""
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        config_content += '''
[prompts]
global_prefix = """
Project Context:
- Python 3.12 monorepo
- Uses Typer for CLI
- Pydantic for validation
"""
'''
        config_file.write_text(config_content)

        result = runner.invoke(app, ["--dry-run", "discover"])

        assert result.exit_code == 0
        assert "Project Context:" in result.stdout
        assert "Python 3.12 monorepo" in result.stdout
        assert "Uses Typer for CLI" in result.stdout

    def test_empty_customization_no_effect(self, runner: CliRunner, initialized_weld: Path) -> None:
        """Empty customization should not affect the prompt."""
        config_file = initialized_weld / ".weld" / "config.toml"
        config_content = config_file.read_text()
        # Add empty prompts section
        config_content += """
[prompts]
"""
        config_file.write_text(config_content)

        result = runner.invoke(app, ["--dry-run", "discover"])

        assert result.exit_code == 0
        # Should still work normally with default prompt
        assert "Analyze" in result.stdout or "architecture" in result.stdout.lower()
