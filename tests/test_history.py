"""Tests for weld.core.history module."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from weld.core.history import (
    HistoryEntry,
    get_history_path,
    log_command,
    prune_history,
    read_history,
)


@pytest.mark.unit
class TestHistoryEntry:
    """Tests for HistoryEntry model."""

    def test_create_entry(self) -> None:
        """Can create a history entry with required fields."""
        entry = HistoryEntry(
            ts=datetime(2026, 1, 4, 12, 0, 0),
            input="/path/to/input.md",
            output="/path/to/output.md",
        )
        assert entry.ts == datetime(2026, 1, 4, 12, 0, 0)
        assert entry.input == "/path/to/input.md"
        assert entry.output == "/path/to/output.md"

    def test_entry_serialization(self) -> None:
        """Entry can be serialized to JSON."""
        entry = HistoryEntry(
            ts=datetime(2026, 1, 4, 12, 0, 0),
            input="input.md",
            output="output.md",
        )
        json_str = entry.model_dump_json()
        data = json.loads(json_str)
        assert "ts" in data
        assert data["input"] == "input.md"
        assert data["output"] == "output.md"

    def test_entry_deserialization(self) -> None:
        """Entry can be deserialized from JSON."""
        json_str = '{"ts": "2026-01-04T12:00:00", "input": "in.md", "output": "out.md"}'
        entry = HistoryEntry.model_validate_json(json_str)
        assert entry.input == "in.md"
        assert entry.output == "out.md"


@pytest.mark.unit
class TestGetHistoryPath:
    """Tests for get_history_path function."""

    def test_returns_correct_path(self, tmp_path: Path) -> None:
        """Returns path to history.jsonl under command directory."""
        weld_dir = tmp_path / ".weld"
        path = get_history_path(weld_dir, "plan")
        assert path == weld_dir / "plan" / "history.jsonl"

    def test_different_commands_have_different_paths(self, tmp_path: Path) -> None:
        """Different commands get different history files."""
        weld_dir = tmp_path / ".weld"
        plan_path = get_history_path(weld_dir, "plan")
        research_path = get_history_path(weld_dir, "research")
        assert plan_path != research_path
        assert plan_path.parent.name == "plan"
        assert research_path.parent.name == "research"


@pytest.mark.unit
class TestLogCommand:
    """Tests for log_command function."""

    def test_creates_history_file(self, tmp_path: Path) -> None:
        """log_command creates history file if it doesn't exist."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        log_command(weld_dir, "plan", "input.md", "output.md")

        history_path = weld_dir / "plan" / "history.jsonl"
        assert history_path.exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """log_command creates parent directories."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        log_command(weld_dir, "plan", "in.md", "out.md")

        assert (weld_dir / "plan").exists()

    def test_appends_to_existing_file(self, tmp_path: Path) -> None:
        """log_command appends to existing history file."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        log_command(weld_dir, "plan", "input1.md", "output1.md")
        log_command(weld_dir, "plan", "input2.md", "output2.md")

        history_path = weld_dir / "plan" / "history.jsonl"
        lines = history_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_entry_contains_timestamp(self, tmp_path: Path) -> None:
        """Log entries contain current timestamp."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        log_command(weld_dir, "plan", "in.md", "out.md")

        history_path = weld_dir / "plan" / "history.jsonl"
        data = json.loads(history_path.read_text().strip())
        assert "ts" in data

    def test_entry_contains_input_output(self, tmp_path: Path) -> None:
        """Log entries contain input and output paths."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        log_command(weld_dir, "plan", "my_input.md", "my_output.md")

        history_path = weld_dir / "plan" / "history.jsonl"
        data = json.loads(history_path.read_text().strip())
        assert data["input"] == "my_input.md"
        assert data["output"] == "my_output.md"


@pytest.mark.unit
class TestReadHistory:
    """Tests for read_history function."""

    def test_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        """Returns empty list when history file doesn't exist."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        result = read_history(weld_dir, "plan")

        assert result == []

    def test_returns_empty_for_empty_file(self, tmp_path: Path) -> None:
        """Returns empty list for empty history file."""
        weld_dir = tmp_path / ".weld"
        history_dir = weld_dir / "plan"
        history_dir.mkdir(parents=True)
        (history_dir / "history.jsonl").write_text("")

        result = read_history(weld_dir, "plan")

        assert result == []

    def test_returns_empty_for_whitespace_only_file(self, tmp_path: Path) -> None:
        """Returns empty list for whitespace-only history file."""
        weld_dir = tmp_path / ".weld"
        history_dir = weld_dir / "plan"
        history_dir.mkdir(parents=True)
        (history_dir / "history.jsonl").write_text("   \n\n   \n")

        result = read_history(weld_dir, "plan")

        assert result == []

    def test_reads_single_entry(self, tmp_path: Path) -> None:
        """Can read a single history entry."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        log_command(weld_dir, "plan", "in.md", "out.md")
        result = read_history(weld_dir, "plan")

        assert len(result) == 1
        assert result[0].input == "in.md"
        assert result[0].output == "out.md"

    def test_reads_multiple_entries_in_order(self, tmp_path: Path) -> None:
        """Reads multiple entries in chronological order (oldest first)."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        log_command(weld_dir, "plan", "first.md", "first_out.md")
        log_command(weld_dir, "plan", "second.md", "second_out.md")
        log_command(weld_dir, "plan", "third.md", "third_out.md")

        result = read_history(weld_dir, "plan")

        assert len(result) == 3
        assert result[0].input == "first.md"
        assert result[1].input == "second.md"
        assert result[2].input == "third.md"

    def test_skips_malformed_json_lines(self, tmp_path: Path) -> None:
        """Skips lines with invalid JSON."""
        weld_dir = tmp_path / ".weld"
        history_dir = weld_dir / "plan"
        history_dir.mkdir(parents=True)

        content = (
            '{"ts": "2026-01-04T12:00:00", "input": "good.md", "output": "out.md"}\n'
            "not valid json\n"
            '{"ts": "2026-01-04T13:00:00", "input": "also_good.md", "output": "out2.md"}\n'
        )
        (history_dir / "history.jsonl").write_text(content)

        result = read_history(weld_dir, "plan")

        assert len(result) == 2
        assert result[0].input == "good.md"
        assert result[1].input == "also_good.md"

    def test_skips_empty_lines(self, tmp_path: Path) -> None:
        """Skips empty lines in history file."""
        weld_dir = tmp_path / ".weld"
        history_dir = weld_dir / "plan"
        history_dir.mkdir(parents=True)

        content = (
            '{"ts": "2026-01-04T12:00:00", "input": "a.md", "output": "out.md"}\n'
            "\n"
            "\n"
            '{"ts": "2026-01-04T13:00:00", "input": "b.md", "output": "out2.md"}\n'
        )
        (history_dir / "history.jsonl").write_text(content)

        result = read_history(weld_dir, "plan")

        assert len(result) == 2


@pytest.mark.unit
class TestPruneHistory:
    """Tests for prune_history function."""

    def test_returns_zero_for_missing_file(self, tmp_path: Path) -> None:
        """Returns 0 when history file doesn't exist."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        result = prune_history(weld_dir, "plan", max_entries=5)

        assert result == 0

    def test_returns_zero_for_empty_file(self, tmp_path: Path) -> None:
        """Returns 0 for empty history file."""
        weld_dir = tmp_path / ".weld"
        history_dir = weld_dir / "plan"
        history_dir.mkdir(parents=True)
        (history_dir / "history.jsonl").write_text("")

        result = prune_history(weld_dir, "plan", max_entries=5)

        assert result == 0

    def test_returns_zero_when_under_limit(self, tmp_path: Path) -> None:
        """Returns 0 when entries are under max limit."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        log_command(weld_dir, "plan", "a.md", "out.md")
        log_command(weld_dir, "plan", "b.md", "out.md")

        result = prune_history(weld_dir, "plan", max_entries=5)

        assert result == 0

    def test_returns_zero_when_unlimited(self, tmp_path: Path) -> None:
        """Returns 0 when max_entries is 0 (unlimited)."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        for i in range(10):
            log_command(weld_dir, "plan", f"{i}.md", "out.md")

        result = prune_history(weld_dir, "plan", max_entries=0)

        assert result == 0
        # All entries should still exist
        assert len(read_history(weld_dir, "plan")) == 10

    def test_prunes_oldest_entries(self, tmp_path: Path) -> None:
        """Prunes oldest entries, keeps newest."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        for i in range(5):
            log_command(weld_dir, "plan", f"file{i}.md", "out.md")

        result = prune_history(weld_dir, "plan", max_entries=2)

        assert result == 3  # Pruned 3 entries
        remaining = read_history(weld_dir, "plan")
        assert len(remaining) == 2
        assert remaining[0].input == "file3.md"  # Second to last
        assert remaining[1].input == "file4.md"  # Last

    def test_returns_count_of_pruned_entries(self, tmp_path: Path) -> None:
        """Returns correct count of pruned entries."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        for i in range(10):
            log_command(weld_dir, "plan", f"{i}.md", "out.md")

        result = prune_history(weld_dir, "plan", max_entries=3)

        assert result == 7

    def test_handles_whitespace_lines(self, tmp_path: Path) -> None:
        """Handles files with whitespace-only lines."""
        weld_dir = tmp_path / ".weld"
        history_dir = weld_dir / "plan"
        history_dir.mkdir(parents=True)

        content = (
            '{"ts": "2026-01-04T12:00:00", "input": "a.md", "output": "out.md"}\n'
            "\n"
            '{"ts": "2026-01-04T13:00:00", "input": "b.md", "output": "out.md"}\n'
            "   \n"
            '{"ts": "2026-01-04T14:00:00", "input": "c.md", "output": "out.md"}\n'
        )
        (history_dir / "history.jsonl").write_text(content)

        result = prune_history(weld_dir, "plan", max_entries=2)

        # Should prune 1 entry (a.md), keeping b.md and c.md
        # Empty lines are filtered out
        assert result == 1
        remaining = read_history(weld_dir, "plan")
        assert len(remaining) == 2


@pytest.mark.unit
class TestHistoryRoundTrip:
    """Integration tests for history logging and reading."""

    def test_log_and_read_roundtrip(self, tmp_path: Path) -> None:
        """Can log entries and read them back."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        log_command(weld_dir, "research", "spec.md", "research.md")
        entries = read_history(weld_dir, "research")

        assert len(entries) == 1
        assert entries[0].input == "spec.md"
        assert entries[0].output == "research.md"
        assert entries[0].ts is not None

    def test_log_prune_read_roundtrip(self, tmp_path: Path) -> None:
        """Can log, prune, and read entries."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        # Log 5 entries
        for i in range(5):
            log_command(weld_dir, "commit", "", f"sha{i}")

        # Prune to 2
        pruned = prune_history(weld_dir, "commit", max_entries=2)
        assert pruned == 3

        # Read back
        entries = read_history(weld_dir, "commit")
        assert len(entries) == 2
        assert entries[0].output == "sha3"
        assert entries[1].output == "sha4"
