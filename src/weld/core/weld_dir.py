"""Weld directory utilities."""

from pathlib import Path

from ..services import get_repo_root


def get_weld_dir(repo_root: Path | None = None) -> Path:
    """Get .weld directory path.

    Args:
        repo_root: Optional repo root, detected if not provided

    Returns:
        Path to .weld directory
    """
    if repo_root is None:
        repo_root = get_repo_root()
    return repo_root / ".weld"


def get_sessions_dir(weld_dir: Path) -> Path:
    """Get or create .weld/sessions directory.

    This directory stores session tracking data including the registry.jsonl
    file that tracks Claude Code sessions and their associated file changes.

    Args:
        weld_dir: Path to the .weld directory

    Returns:
        Path to .weld/sessions directory (created if it doesn't exist)
    """
    sessions_dir = weld_dir / "sessions"
    sessions_dir.mkdir(exist_ok=True)
    return sessions_dir
