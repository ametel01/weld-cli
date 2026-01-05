"""Command history tracking for weld."""

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class HistoryEntry(BaseModel):
    """A single command history entry."""

    ts: datetime
    input: str
    output: str


def get_history_path(weld_dir: Path, command: str) -> Path:
    """Get path to history file for a command.

    Args:
        weld_dir: Path to .weld directory
        command: Command name (e.g., "plan", "research")

    Returns:
        Path to history.jsonl file
    """
    return weld_dir / command / "history.jsonl"


def log_command(weld_dir: Path, command: str, input_path: str, output_path: str) -> None:
    """Log a command execution to history.

    Args:
        weld_dir: Path to .weld directory
        command: Command name
        input_path: Path to input file
        output_path: Path to output file
    """
    history_path = get_history_path(weld_dir, command)
    history_path.parent.mkdir(parents=True, exist_ok=True)

    entry = HistoryEntry(
        ts=datetime.now(),
        input=input_path,
        output=output_path,
    )

    with history_path.open("a") as f:
        f.write(entry.model_dump_json() + "\n")


def prune_history(weld_dir: Path, command: str, max_entries: int) -> int:
    """Prune old history entries, keeping only max_entries.

    Args:
        weld_dir: Path to .weld directory
        command: Command name
        max_entries: Maximum entries to keep (0 = unlimited)

    Returns:
        Number of entries pruned
    """
    if max_entries <= 0:
        return 0

    history_path = get_history_path(weld_dir, command)
    if not history_path.exists():
        return 0

    content = history_path.read_text()
    if not content.strip():
        return 0

    # Filter to only non-empty lines
    lines = [line for line in content.splitlines() if line.strip()]
    if len(lines) <= max_entries:
        return 0

    pruned = len(lines) - max_entries
    kept_lines = lines[-max_entries:]
    history_path.write_text("\n".join(kept_lines) + "\n")
    return pruned


def read_history(weld_dir: Path, command: str) -> list[HistoryEntry]:
    """Read command history entries.

    Args:
        weld_dir: Path to .weld directory
        command: Command name

    Returns:
        List of history entries (oldest first)
    """
    history_path = get_history_path(weld_dir, command)
    if not history_path.exists():
        return []

    content = history_path.read_text()
    if not content.strip():
        return []

    entries = []
    for line in content.splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(HistoryEntry.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValueError):
                continue
    return entries
