"""Prompt customization utilities.

This module provides functions to apply user-configured customizations
to prompts before they are sent to AI providers. Customizations include
prefix/suffix text and default focus areas.
"""

from ..config import PromptsConfig, TaskType


def apply_customization(
    prompt: str,
    task: TaskType,
    prompts_config: PromptsConfig,
) -> str:
    """Apply prefix/suffix customization to a prompt.

    Retrieves the effective customization for the given task (merged with
    global defaults) and wraps the prompt with configured prefix and suffix.

    Args:
        prompt: The original prompt text
        task: The task type (e.g., TaskType.RESEARCH, TaskType.PLAN_GENERATION)
        prompts_config: The prompts configuration from WeldConfig

    Returns:
        The prompt with prefix and suffix applied. If neither is configured,
        returns the original prompt unchanged.

    Example:
        >>> config = PromptsConfig(default=PromptCustomization(
        ...     prefix="Context: Python project",
        ...     suffix="Use type hints"
        ... ))
        >>> apply_customization("Analyze this code", TaskType.RESEARCH, config)
        'Context: Python project\\n\\nAnalyze this code\\n\\nUse type hints'
    """
    customization = prompts_config.get_effective_customization(task)

    parts: list[str] = []

    if customization.prefix:
        parts.append(customization.prefix)

    parts.append(prompt)

    if customization.suffix:
        parts.append(customization.suffix)

    # Join with double newlines for clear separation
    return "\n\n".join(parts)


def get_default_focus(
    task: TaskType,
    prompts_config: PromptsConfig,
) -> str | None:
    """Get the default focus for a task type.

    Returns the configured default_focus for the task, falling back to
    the global default if the task-specific value is not set.

    Args:
        task: The task type to get the default focus for
        prompts_config: The prompts configuration from WeldConfig

    Returns:
        The default focus string, or None if not configured.

    Example:
        >>> config = PromptsConfig(research=PromptCustomization(
        ...     default_focus="security"
        ... ))
        >>> get_default_focus(TaskType.RESEARCH, config)
        'security'
    """
    customization = prompts_config.get_effective_customization(task)
    return customization.default_focus
