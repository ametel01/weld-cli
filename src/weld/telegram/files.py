"""File path validation for Telegram bot /fetch and /push commands."""

from pathlib import Path

from weld.telegram.config import TelegramConfig


class FilePathError(Exception):
    """Base exception for file path validation errors."""


class PathTraversalError(FilePathError):
    """Raised when path traversal is detected."""


class PathNotAllowedError(FilePathError):
    """Raised when path is not within an allowed project directory."""


class PathNotFoundError(FilePathError):
    """Raised when path does not exist (for fetch operations)."""


def _resolve_and_validate_base(
    path: str | Path,
    config: TelegramConfig,
    *,
    must_exist: bool,
) -> tuple[Path, Path]:
    """Resolve path and validate it's within an allowed project directory.

    Args:
        path: The path to validate (relative or absolute)
        config: Telegram configuration with registered projects
        must_exist: If True, raises PathNotFoundError if path doesn't exist

    Returns:
        Tuple of (resolved_path, project_root) where resolved_path is the
        fully resolved absolute path and project_root is the project directory
        it belongs to.

    Raises:
        PathNotAllowedError: If path is not within any registered project
        PathNotFoundError: If must_exist=True and path doesn't exist
        PathTraversalError: If path attempts traversal outside project root
    """
    if not config.projects:
        raise PathNotAllowedError("No projects registered in configuration")

    path = Path(path)

    # For must_exist=True (fetch), we need to resolve symlinks to check real location
    # For must_exist=False (push), we resolve what exists and keep the rest
    if must_exist:
        if not path.exists():
            raise PathNotFoundError(f"Path does not exist: {path}")
        # Resolve symlinks to get the real path for security check
        resolved = path.resolve(strict=True)
    else:
        # For push: resolve parent if it exists, then append filename
        # This handles the case where the file doesn't exist yet
        try:
            # Try strict resolution first
            resolved = path.resolve(strict=True)
        except (FileNotFoundError, OSError):
            # File doesn't exist - resolve parent and append filename
            parent = path.parent
            if parent.exists():
                resolved = parent.resolve(strict=True) / path.name
            else:
                # Neither file nor parent exists - use non-strict resolution
                # but verify no symlink shenanigans in existing parts
                resolved = path.resolve(strict=False)

    # Check if resolved path is within any registered project
    for project in config.projects:
        project_root = project.path.resolve()
        try:
            resolved.relative_to(project_root)
            return resolved, project_root
        except ValueError:
            # Not within this project, try next
            continue

    # Path is not within any project
    project_paths = ", ".join(str(p.path) for p in config.projects)
    raise PathNotAllowedError(
        f"Path '{resolved}' is not within any registered project. "
        f"Registered projects: {project_paths}"
    )


def validate_fetch_path(path: str | Path, config: TelegramConfig) -> Path:
    """Validate a path for /fetch operations.

    Ensures the path:
    - Exists on the filesystem
    - Resolves (following symlinks) to a location within a registered project
    - Does not escape the project root via symlinks or traversal

    Args:
        path: The path to fetch (relative or absolute)
        config: Telegram configuration with registered projects

    Returns:
        The resolved absolute path that is safe to read

    Raises:
        PathNotFoundError: If path doesn't exist
        PathNotAllowedError: If path is not within any registered project
        PathTraversalError: If path attempts traversal outside project root
    """
    resolved, _ = _resolve_and_validate_base(path, config, must_exist=True)
    return resolved


def validate_push_path(path: str | Path, config: TelegramConfig) -> Path:
    """Validate a path for /push operations.

    Ensures the path:
    - Would resolve to a location within a registered project
    - Does not escape the project root via symlinks or traversal
    - The file doesn't need to exist yet (for new files)

    Args:
        path: The path to push to (relative or absolute)
        config: Telegram configuration with registered projects

    Returns:
        The resolved absolute path that is safe to write

    Raises:
        PathNotAllowedError: If path is not within any registered project
        PathTraversalError: If path attempts traversal outside project root
    """
    resolved, _ = _resolve_and_validate_base(path, config, must_exist=False)
    return resolved
