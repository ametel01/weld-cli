"""Filesystem I/O operations for weld.

This module provides common file I/O utilities used across the codebase.
"""

from pathlib import Path


def ensure_directory(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path to ensure exists

    Returns:
        The path that was created/verified
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_file(path: Path, content: str) -> None:
    """Write content to a file, creating parent directories if needed.

    Args:
        path: File path to write to
        content: Content to write
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def read_file(path: Path) -> str:
    """Read content from a file.

    Args:
        path: File path to read from

    Returns:
        File content as string

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    return path.read_text()


def read_file_optional(path: Path, default: str = "") -> str:
    """Read content from a file, returning default if it doesn't exist.

    Args:
        path: File path to read from
        default: Default value if file doesn't exist

    Returns:
        File content or default value
    """
    if path.exists():
        return path.read_text()
    return default


def file_exists(path: Path) -> bool:
    """Check if a file exists.

    Args:
        path: File path to check

    Returns:
        True if file exists
    """
    return path.exists() and path.is_file()


def dir_exists(path: Path) -> bool:
    """Check if a directory exists.

    Args:
        path: Directory path to check

    Returns:
        True if directory exists
    """
    return path.exists() and path.is_dir()
