"""Next command - shortcut to continue with next action."""

import typer

from ..core import get_weld_dir
from ..models import Meta
from ..output import get_output_context
from ..services.git import GitError, get_repo_root


def next_action() -> None:
    """Show and optionally execute the next action for the current run."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    runs_dir = weld_dir / "runs"

    if not runs_dir.exists():
        ctx.console.print("No runs found.")
        ctx.console.print("  Start with: weld run start --spec <file>")
        return

    # Find most recent non-abandoned run
    runs = sorted(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    current_run = None

    for run_dir in runs:
        meta_path = run_dir / "meta.json"
        if meta_path.exists():
            meta = Meta.model_validate_json(meta_path.read_text())
            if not meta.abandoned:
                current_run = run_dir
                break

    if current_run is None:
        ctx.console.print("No active runs found.")
        ctx.console.print("  Start with: weld run start --spec <file>")
        return

    # Use status command to show next action
    from .status import status as show_status

    show_status(run=current_run.name)
