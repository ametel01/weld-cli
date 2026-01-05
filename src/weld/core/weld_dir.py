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
