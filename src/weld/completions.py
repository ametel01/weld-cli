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


def complete_export_format(incomplete: str) -> list[str]:
    """Return export format options that start with the given prefix.

    Used for shell completion of --format arguments in export commands.
    Returns toml and json always, plus yaml if pyyaml is installed.

    Args:
        incomplete: The partial string typed by the user

    Returns:
        List of matching format names, alphabetically sorted
    """
    formats = ["json", "toml"]

    # Add yaml if pyyaml is available
    try:
        import yaml  # noqa: F401

        formats.append("yaml")
    except ImportError:
        pass

    # Sort alphabetically and filter by prefix
    return sorted(f for f in formats if f.startswith(incomplete.lower()))
