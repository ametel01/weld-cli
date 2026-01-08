"""Tests for session tracking models."""

from datetime import UTC, datetime

from weld.models.session import SessionActivity, TrackedSession


class TestSessionActivity:
    """Tests for SessionActivity model."""

    def test_creates_with_required_fields(self) -> None:
        """SessionActivity should require command and timestamp."""
        now = datetime.now(UTC)
        activity = SessionActivity(
            command="implement",
            timestamp=now,
        )
        assert activity.command == "implement"
        assert activity.timestamp == now
        assert activity.files_created == []
        assert activity.files_modified == []
        assert activity.completed is True

    def test_files_lists_default_to_empty(self) -> None:
        """SessionActivity should default file lists to empty."""
        activity = SessionActivity(
            command="research",
            timestamp=datetime.now(UTC),
        )
        assert activity.files_created == []
        assert activity.files_modified == []

    def test_completed_defaults_to_true(self) -> None:
        """SessionActivity should default completed to True."""
        activity = SessionActivity(
            command="plan",
            timestamp=datetime.now(UTC),
        )
        assert activity.completed is True

    def test_accepts_file_lists(self) -> None:
        """SessionActivity should accept file lists."""
        activity = SessionActivity(
            command="implement",
            timestamp=datetime.now(UTC),
            files_created=["src/new.py", "tests/test_new.py"],
            files_modified=["src/existing.py"],
        )
        assert activity.files_created == ["src/new.py", "tests/test_new.py"]
        assert activity.files_modified == ["src/existing.py"]

    def test_accepts_completed_false(self) -> None:
        """SessionActivity should accept completed=False for interruptions."""
        activity = SessionActivity(
            command="implement",
            timestamp=datetime.now(UTC),
            completed=False,
        )
        assert activity.completed is False

    def test_serializes_to_json(self) -> None:
        """SessionActivity should serialize to JSON."""
        now = datetime.now(UTC)
        activity = SessionActivity(
            command="implement",
            timestamp=now,
            files_created=["test.py"],
            completed=True,
        )
        json_str = activity.model_dump_json()
        assert "implement" in json_str
        assert "test.py" in json_str

    def test_deserializes_from_json(self) -> None:
        """SessionActivity should deserialize from JSON."""
        now = datetime.now(UTC)
        original = SessionActivity(
            command="research",
            timestamp=now,
            files_modified=["doc.md"],
        )
        json_str = original.model_dump_json()
        restored = SessionActivity.model_validate_json(json_str)
        assert restored.command == "research"
        assert restored.files_modified == ["doc.md"]


class TestTrackedSession:
    """Tests for TrackedSession model."""

    def test_creates_with_required_fields(self) -> None:
        """TrackedSession should require session_id, session_file, and timestamps."""
        now = datetime.now(UTC)
        session = TrackedSession(
            session_id="abc123-def456",
            session_file="/home/user/.claude/projects/test/abc123.jsonl",
            first_seen=now,
            last_activity=now,
        )
        assert session.session_id == "abc123-def456"
        assert session.session_file == "/home/user/.claude/projects/test/abc123.jsonl"
        assert session.first_seen == now
        assert session.last_activity == now
        assert session.activities == []

    def test_activities_default_to_empty(self) -> None:
        """TrackedSession should default activities to empty list."""
        now = datetime.now(UTC)
        session = TrackedSession(
            session_id="abc123",
            session_file="/path/to/session.jsonl",
            first_seen=now,
            last_activity=now,
        )
        assert session.activities == []

    def test_accepts_activities_list(self) -> None:
        """TrackedSession should accept activities list."""
        now = datetime.now(UTC)
        activities = [
            SessionActivity(command="research", timestamp=now),
            SessionActivity(command="plan", timestamp=now),
        ]
        session = TrackedSession(
            session_id="abc123",
            session_file="/path/to/session.jsonl",
            first_seen=now,
            last_activity=now,
            activities=activities,
        )
        assert len(session.activities) == 2
        assert session.activities[0].command == "research"
        assert session.activities[1].command == "plan"

    def test_serializes_to_json(self) -> None:
        """TrackedSession should serialize to JSON including activities."""
        now = datetime.now(UTC)
        session = TrackedSession(
            session_id="abc123-def456",
            session_file="/path/to/session.jsonl",
            first_seen=now,
            last_activity=now,
            activities=[SessionActivity(command="implement", timestamp=now)],
        )
        json_str = session.model_dump_json()
        assert "abc123-def456" in json_str
        assert "implement" in json_str

    def test_deserializes_from_json(self) -> None:
        """TrackedSession should deserialize from JSON."""
        now = datetime.now(UTC)
        original = TrackedSession(
            session_id="test-session",
            session_file="/path/to/session.jsonl",
            first_seen=now,
            last_activity=now,
            activities=[
                SessionActivity(
                    command="research",
                    timestamp=now,
                    files_created=["research.md"],
                )
            ],
        )
        json_str = original.model_dump_json()
        restored = TrackedSession.model_validate_json(json_str)
        assert restored.session_id == "test-session"
        assert len(restored.activities) == 1
        assert restored.activities[0].files_created == ["research.md"]

    def test_roundtrip_preserves_data(self) -> None:
        """Serialization roundtrip should preserve all data."""
        now = datetime.now(UTC)
        original = TrackedSession(
            session_id="full-test",
            session_file="/absolute/path/session.jsonl",
            first_seen=now,
            last_activity=now,
            activities=[
                SessionActivity(
                    command="implement",
                    timestamp=now,
                    files_created=["new.py"],
                    files_modified=["existing.py"],
                    completed=False,
                ),
            ],
        )
        json_str = original.model_dump_json()
        restored = TrackedSession.model_validate_json(json_str)

        assert restored.session_id == original.session_id
        assert restored.session_file == original.session_file
        assert restored.activities[0].completed is False
        assert restored.activities[0].files_created == ["new.py"]
        assert restored.activities[0].files_modified == ["existing.py"]
