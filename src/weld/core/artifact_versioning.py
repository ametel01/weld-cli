"""Artifact versioning manager for research and plan documents.

Maintains version history with automatic pruning to MAX_VERSIONS (5).
Each version is stored in history/v<N>/ with content.md and meta.json.

Version numbering:
- 0 means no versions exist yet
- First snapshot creates v1
- Second snapshot creates v2, etc.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from ..models import MAX_VERSIONS, VersionInfo

logger = logging.getLogger(__name__)


def get_current_version(artifact_dir: Path) -> int:
    """Get current version number from artifact directory.

    Args:
        artifact_dir: Path to research/ or plan/ directory

    Returns:
        Current version number (0 if no history exists)
    """
    history_dir = artifact_dir / "history"
    if not history_dir.exists():
        return 0

    versions = [
        int(d.name[1:])  # Extract N from "vN"
        for d in history_dir.iterdir()
        if d.is_dir() and d.name.startswith("v") and d.name[1:].isdigit()
    ]
    return max(versions) if versions else 0


def create_version_snapshot(
    artifact_dir: Path,
    content_file: str,
    trigger_reason: str,
    review_id: str | None = None,
) -> int:
    """Create a new version snapshot of an artifact.

    Args:
        artifact_dir: Path to research/ or plan/ directory
        content_file: Name of the content file (e.g., "research.md", "plan.md")
        trigger_reason: Why this version was created
        review_id: Optional review ID that triggered the new version

    Returns:
        The new version number (0 if no content to version)
    """
    content_path = artifact_dir / content_file
    if not content_path.exists():
        return 0  # No content to version yet

    history_dir = artifact_dir / "history"
    history_dir.mkdir(exist_ok=True)

    # Determine new version number (first snapshot is v1)
    current = get_current_version(artifact_dir)
    new_version = current + 1

    # Create version directory
    version_dir = history_dir / f"v{new_version}"
    version_dir.mkdir(exist_ok=True)

    # Copy content
    shutil.copy2(content_path, version_dir / "content.md")

    # Write version metadata
    version_info = VersionInfo(
        version=new_version,
        trigger_reason=trigger_reason,
        review_id=review_id,
    )
    (version_dir / "meta.json").write_text(version_info.model_dump_json(indent=2))

    # Mark previous version as superseded (only if a previous version exists)
    if current >= 1:
        prev_meta_path = history_dir / f"v{current}" / "meta.json"
        if prev_meta_path.exists():
            try:
                prev_info = VersionInfo.model_validate_json(prev_meta_path.read_text())
                prev_info.superseded_at = datetime.now()
                prev_meta_path.write_text(prev_info.model_dump_json(indent=2))
            except (ValidationError, OSError) as e:
                logger.warning("Failed to update superseded_at for v%d: %s", current, e)

    # Prune old versions (keep only MAX_VERSIONS)
    _prune_old_versions(history_dir)

    return new_version


def _prune_old_versions(history_dir: Path) -> None:
    """Remove versions beyond MAX_VERSIONS, keeping newest.

    Args:
        history_dir: Path to history/ directory
    """
    version_dirs = sorted(
        [d for d in history_dir.iterdir() if d.is_dir() and d.name.startswith("v")],
        key=lambda d: int(d.name[1:]),
        reverse=True,  # Newest first
    )

    for old_dir in version_dirs[MAX_VERSIONS:]:
        shutil.rmtree(old_dir)


def get_version_history(artifact_dir: Path) -> list[VersionInfo]:
    """Get version history for an artifact.

    Args:
        artifact_dir: Path to research/ or plan/ directory

    Returns:
        List of VersionInfo, newest first. Corrupt entries are skipped.
    """
    history_dir = artifact_dir / "history"
    if not history_dir.exists():
        return []

    versions = []
    for version_dir in history_dir.iterdir():
        if version_dir.is_dir() and version_dir.name.startswith("v"):
            meta_path = version_dir / "meta.json"
            if meta_path.exists():
                try:
                    versions.append(VersionInfo.model_validate_json(meta_path.read_text()))
                except (ValidationError, OSError) as e:
                    logger.warning("Skipping corrupt version %s: %s", version_dir.name, e)

    return sorted(versions, key=lambda v: v.version, reverse=True)


def restore_version(artifact_dir: Path, version: int, content_file: str) -> bool:
    """Restore a previous version as current.

    Args:
        artifact_dir: Path to research/ or plan/ directory
        version: Version number to restore
        content_file: Name of the content file

    Returns:
        True if restored successfully
    """
    version_content = artifact_dir / "history" / f"v{version}" / "content.md"
    if not version_content.exists():
        return False

    # First, snapshot current as new version
    create_version_snapshot(artifact_dir, content_file, f"pre-restore from v{version}")

    # Then copy old content to current
    shutil.copy2(version_content, artifact_dir / content_file)
    return True


def update_run_meta_version(
    run_dir: Path,
    artifact_type: str,
    new_version: int,
) -> bool:
    """Update the run's meta.json with new artifact version number.

    Args:
        run_dir: Path to the run directory (containing meta.json)
        artifact_type: Either "research" or "plan"
        new_version: The new version number to record

    Returns:
        True if updated successfully, False otherwise
    """
    from ..models import Meta

    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        logger.warning("meta.json not found at %s", meta_path)
        return False

    try:
        meta = Meta.model_validate_json(meta_path.read_text())

        if artifact_type == "research":
            meta.research_version = new_version
        elif artifact_type == "plan":
            meta.plan_version = new_version
        else:
            logger.warning("Unknown artifact type: %s", artifact_type)
            return False

        meta_path.write_text(meta.model_dump_json(indent=2))
        return True
    except (ValidationError, OSError) as e:
        logger.warning("Failed to update meta.json version: %s", e)
        return False
