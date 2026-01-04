"""Diff capture utilities for weld."""

from pathlib import Path

from .git import get_diff


def capture_diff(repo_root: Path, staged: bool = False) -> tuple[str, bool]:
    """Capture diff and return (content, is_nonempty).

    Args:
        repo_root: Repository root directory
        staged: If True, capture staged changes only

    Returns:
        Tuple of (diff content, True if diff is non-empty)
    """
    diff_content = get_diff(staged=staged, cwd=repo_root)
    return diff_content, bool(diff_content.strip())


def write_diff(path: Path, content: str) -> None:
    """Write diff to file.

    Args:
        path: File path to write to
        content: Diff content
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
