"""Prompt customization utilities.

This module provides functions to apply user-configured customizations
to prompts before they are sent to AI providers. Customizations include
prefix/suffix text and default focus areas.
"""

from ..config import PromptsConfig, TaskType, WeldConfig


def apply_customization(
    prompt: str,
    task: TaskType | str,
    config: WeldConfig | PromptsConfig,
) -> str:
    """Apply layered prefix/suffix customization to a prompt.

    Applies customizations in this order:
        global_prefix → task_prefix → prompt → task_suffix → global_suffix

    This layered approach allows both project-wide context (global) and
    task-specific instructions to be applied together.

    Args:
        prompt: The original prompt text
        task: The task type (TaskType enum or string value like 'discover')
        config: WeldConfig or PromptsConfig containing customization settings

    Returns:
        The prompt with all applicable prefixes and suffixes applied.
        If no customizations are configured, returns the original prompt.

    Example:
        >>> config = WeldConfig(prompts=PromptsConfig(
        ...     global_prefix="This is a Python project.",
        ...     discover=PromptCustomization(prefix="Focus on architecture.")
        ... ))
        >>> apply_customization("Analyze the codebase", "discover", config)
        'This is a Python project.\\n\\nFocus on architecture.\\n\\nAnalyze the codebase'
    """
    # Extract PromptsConfig if given WeldConfig
    prompts_config = config.prompts if isinstance(config, WeldConfig) else config

    # Normalize task to TaskType enum
    if isinstance(task, str):
        task = TaskType(task)

    # Get task-specific customization
    task_custom = prompts_config.get_customization(task)

    parts: list[str] = []

    # Layer 1: Global prefix (outermost)
    if prompts_config.global_prefix:
        parts.append(prompts_config.global_prefix)

    # Layer 2: Task-specific prefix
    if task_custom.prefix:
        parts.append(task_custom.prefix)

    # Layer 3: The actual prompt
    parts.append(prompt)

    # Layer 4: Task-specific suffix
    if task_custom.suffix:
        parts.append(task_custom.suffix)

    # Layer 5: Global suffix (outermost)
    if prompts_config.global_suffix:
        parts.append(prompts_config.global_suffix)

    # Join with double newlines for clear separation
    return "\n\n".join(parts)


def get_default_focus(
    task: TaskType | str,
    config: WeldConfig | PromptsConfig,
    explicit_focus: str | None = None,
) -> str | None:
    """Get the effective focus for a task type.

    Returns the explicit focus if provided, otherwise falls back to
    the configured default_focus for the task.

    Args:
        task: The task type (TaskType enum or string value)
        config: WeldConfig or PromptsConfig containing customization settings
        explicit_focus: Optional explicit focus from command line (takes precedence)

    Returns:
        The explicit focus if provided (non-empty string),
        otherwise the configured default_focus, or None if neither is set.

    Example:
        >>> config = PromptsConfig(research=PromptCustomization(
        ...     default_focus="security"
        ... ))
        >>> get_default_focus(TaskType.RESEARCH, config)
        'security'
        >>> get_default_focus(TaskType.RESEARCH, config, "performance")
        'performance'
    """
    # Return explicit focus if provided (non-empty string takes precedence)
    if explicit_focus:
        return explicit_focus

    # Extract PromptsConfig if given WeldConfig
    prompts_config = config.prompts if isinstance(config, WeldConfig) else config

    # Normalize task to TaskType enum
    if isinstance(task, str):
        task = TaskType(task)

    customization = prompts_config.get_customization(task)
    return customization.default_focus
