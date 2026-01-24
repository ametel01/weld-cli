"""Shell completion helpers for weld CLI."""

from weld.config import TaskType


def complete_task_type(incomplete: str) -> list[str]:
    """Return TaskType values that start with the given prefix.

    Used for shell completion of task type arguments in CLI commands.

    Args:
        incomplete: The partial string typed by the user

    Returns:
        List of matching TaskType values (lowercase strings)
    """
    return [t.value for t in TaskType if t.value.startswith(incomplete.lower())]
