"""Run management utilities for weld."""

import hashlib
import re
from datetime import datetime
from pathlib import Path

from .config import WeldConfig
from .git import get_current_branch, get_head_sha, get_repo_root
from .models import Meta, SpecRef


def generate_run_id(slug: str | None = None, spec_path: Path | None = None) -> str:
    """Generate run ID in format YYYYMMDD-HHMMSS-<slug>.

    Args:
        slug: Optional slug to use
        spec_path: Optional spec file path to derive slug from

    Returns:
        Generated run ID
    """
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d-%H%M%S")

    if slug:
        safe_slug = sanitize_slug(slug)
    elif spec_path:
        safe_slug = sanitize_slug(spec_path.stem)
    else:
        safe_slug = "run"

    return f"{timestamp}-{safe_slug}"


def sanitize_slug(name: str) -> str:
    """Convert name to safe slug.

    Args:
        name: Name to sanitize

    Returns:
        Lowercase slug with only alphanumeric and hyphens
    """
    # Lowercase, replace spaces/special chars with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    return slug[:50] if slug else "unnamed"


def hash_file(path: Path) -> str:
    """Compute SHA256 of file.

    Args:
        path: File path

    Returns:
        Hex-encoded SHA256 hash
    """
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def hash_config(config: WeldConfig) -> str:
    """Compute hash of config for change detection.

    Args:
        config: Weld configuration

    Returns:
        First 16 chars of SHA256 hash
    """
    return hashlib.sha256(config.model_dump_json().encode()).hexdigest()[:16]


def create_run_directory(weld_dir: Path, run_id: str) -> Path:
    """Create run directory structure.

    Args:
        weld_dir: Path to .weld directory
        run_id: Run ID

    Returns:
        Path to created run directory
    """
    run_dir = weld_dir / "runs" / run_id

    # Create subdirectories
    (run_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (run_dir / "plan").mkdir(parents=True, exist_ok=True)
    (run_dir / "steps").mkdir(parents=True, exist_ok=True)
    (run_dir / "commit").mkdir(parents=True, exist_ok=True)

    return run_dir


def create_meta(
    run_id: str,
    repo_root: Path,
    config: WeldConfig,
) -> Meta:
    """Create run metadata.

    Args:
        run_id: Run ID
        repo_root: Repository root path
        config: Weld configuration

    Returns:
        Meta model instance
    """
    return Meta(
        run_id=run_id,
        repo_root=repo_root,
        branch=get_current_branch(cwd=repo_root),
        head_sha=get_head_sha(cwd=repo_root),
        config_hash=hash_config(config),
    )


def create_spec_ref(spec_path: Path) -> SpecRef:
    """Create spec file reference.

    Args:
        spec_path: Path to specification file

    Returns:
        SpecRef model instance
    """
    return SpecRef(
        absolute_path=spec_path.resolve(),
        sha256=hash_file(spec_path),
        size_bytes=spec_path.stat().st_size,
    )


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


def get_run_dir(weld_dir: Path, run_id: str) -> Path:
    """Get run directory path.

    Args:
        weld_dir: Path to .weld directory
        run_id: Run ID

    Returns:
        Path to run directory
    """
    return weld_dir / "runs" / run_id


def list_runs(weld_dir: Path) -> list[str]:
    """List all run IDs.

    Args:
        weld_dir: Path to .weld directory

    Returns:
        List of run IDs, sorted newest first
    """
    runs_dir = weld_dir / "runs"
    if not runs_dir.exists():
        return []
    return sorted([d.name for d in runs_dir.iterdir() if d.is_dir()], reverse=True)
