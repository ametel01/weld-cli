"""Input validation utilities."""

import re
from pathlib import Path


class ValidationError(Exception):
    """Validation failed."""

    pass


def validate_path_within_repo(path: Path, repo_root: Path) -> Path:
    """Ensure path is within repository bounds.

    Args:
        path: Path to validate
        repo_root: Repository root directory

    Returns:
        Resolved absolute path

    Raises:
        ValidationError: If path escapes repository
    """
    resolved = path.resolve()
    repo_resolved = repo_root.resolve()

    try:
        resolved.relative_to(repo_resolved)
    except ValueError:
        raise ValidationError(f"Path {path} is outside repository {repo_root}") from None

    return resolved


def validate_run_id(run_id: str) -> str:
    """Validate run ID format.

    Args:
        run_id: Run ID to validate

    Returns:
        Validated run ID

    Raises:
        ValidationError: If run ID is invalid
    """
    # Format: YYYYMMDD-HHMMSS-slug
    pattern = r"^\d{8}-\d{6}-[a-z0-9-]+$"
    if not re.match(pattern, run_id):
        raise ValidationError(f"Invalid run ID format: {run_id}. Expected: YYYYMMDD-HHMMSS-slug")

    return run_id
