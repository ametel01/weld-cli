"""Shell completion helpers for weld CLI."""

from pathlib import Path

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


def complete_markdown_file(incomplete: str) -> list[str]:
    """Return markdown files and directories matching the given path prefix.

    Used for shell completion of markdown file arguments in CLI commands.
    Provides file system path completion filtered to .md files only.

    Args:
        incomplete: The partial path typed by the user (may be empty)

    Returns:
        List of matching paths, alphabetically sorted, capped at 20 results.
        Directories include a trailing slash to indicate they can be expanded.
    """
    max_results = 20

    # Handle empty input - start from current directory
    if not incomplete:
        search_dir = Path(".")
        prefix = ""
    else:
        path = Path(incomplete)
        # If the incomplete path ends with /, list contents of that directory
        if incomplete.endswith("/") or incomplete.endswith("\\"):
            search_dir = path
            prefix = ""
        # Otherwise, search in the parent directory for matches
        elif path.is_dir():
            # User typed a directory name without trailing slash
            search_dir = path
            prefix = ""
        else:
            search_dir = path.parent if path.parent != path else Path(".")
            prefix = path.name

    results: list[str] = []

    try:
        if not search_dir.exists() or not search_dir.is_dir():
            return []

        for entry in search_dir.iterdir():
            # Skip hidden files
            if entry.name.startswith("."):
                continue

            # Check if name matches prefix
            if prefix and not entry.name.lower().startswith(prefix.lower()):
                continue

            try:
                if entry.is_dir():
                    # Add directories with trailing slash
                    results.append(str(entry) + "/")
                elif entry.is_file() and entry.suffix.lower() == ".md":
                    # Add markdown files
                    results.append(str(entry))
            except PermissionError:
                # Skip entries we can't access
                continue

    except PermissionError:
        # Can't read directory, return empty
        return []

    # Sort alphabetically and cap at max_results
    return sorted(results)[:max_results]


def complete_step_number(incomplete: str) -> list[str]:
    """Return step numbers that start with the given prefix.

    Used for shell completion of step number arguments in CLI commands.
    Returns static step numbers 1.1-3.3 as fallback suggestions when
    dynamic plan parsing is not available.

    Args:
        incomplete: The partial string typed by the user

    Returns:
        List of matching step numbers in format "X.Y"
    """
    # Static fallback step numbers covering 3 phases with 3 steps each
    step_numbers = [
        "1.1",
        "1.2",
        "1.3",
        "2.1",
        "2.2",
        "2.3",
        "3.1",
        "3.2",
        "3.3",
    ]

    return [s for s in step_numbers if s.startswith(incomplete)]


def complete_phase_number(incomplete: str) -> list[str]:
    """Return phase numbers that start with the given prefix.

    Used for shell completion of phase number arguments in CLI commands.
    Returns static phase numbers 1-5 as suggestions.

    Args:
        incomplete: The partial string typed by the user

    Returns:
        List of matching phase numbers as strings
    """
    phase_numbers = ["1", "2", "3", "4", "5"]

    return [p for p in phase_numbers if p.startswith(incomplete)]
