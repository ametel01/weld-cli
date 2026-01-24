"""Tests for Telegram bot state store."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from weld.telegram.config import TelegramConfig, TelegramProject
from weld.telegram.state import (
    Project,
    Run,
    StateStore,
    UserContext,
)


@pytest.fixture
async def state_store():
    """Create an in-memory state store for testing."""
    async with StateStore(":memory:") as store:
        yield store


@pytest.mark.asyncio
@pytest.mark.unit
class TestStateStoreInit:
    """Tests for StateStore initialization."""

    async def test_init_creates_schema(self) -> None:
        """init() should create database schema."""
        store = StateStore(":memory:")
        await store.init()
        try:
            # Schema should exist - can query tables
            assert store._conn is not None
            async with store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) as cursor:
                tables = [row["name"] async for row in cursor]
            assert "contexts" in tables
            assert "projects" in tables
            assert "runs" in tables
            assert "schema_version" in tables
        finally:
            await store.close()

    async def test_context_manager(self) -> None:
        """StateStore works as async context manager."""
        async with StateStore(":memory:") as store:
            assert store._conn is not None
        # Connection should be closed after exit
        assert store._conn is None

    async def test_close_idempotent(self) -> None:
        """close() can be called multiple times safely."""
        store = StateStore(":memory:")
        await store.init()
        await store.close()
        await store.close()  # Should not raise


@pytest.mark.asyncio
@pytest.mark.unit
class TestUserContextCRUD:
    """Tests for UserContext CRUD operations."""

    async def test_get_context_not_found(self, state_store: StateStore) -> None:
        """get_context returns None when user doesn't exist."""
        result = await state_store.get_context(12345)
        assert result is None

    async def test_upsert_and_get_context(self, state_store: StateStore) -> None:
        """Can create and retrieve user context."""
        context = UserContext(
            user_id=12345,
            current_project="myproject",
            conversation_state="awaiting_command",
            last_message_id=100,
        )
        await state_store.upsert_context(context)

        result = await state_store.get_context(12345)
        assert result is not None
        assert result.user_id == 12345
        assert result.current_project == "myproject"
        assert result.conversation_state == "awaiting_command"
        assert result.last_message_id == 100

    async def test_upsert_updates_existing(self, state_store: StateStore) -> None:
        """upsert_context updates existing context."""
        # Create initial context
        context1 = UserContext(user_id=12345, current_project="proj1")
        await state_store.upsert_context(context1)

        # Update it
        context2 = UserContext(
            user_id=12345,
            current_project="proj2",
            conversation_state="running",
        )
        await state_store.upsert_context(context2)

        result = await state_store.get_context(12345)
        assert result is not None
        assert result.current_project == "proj2"
        assert result.conversation_state == "running"

    async def test_delete_context_success(self, state_store: StateStore) -> None:
        """delete_context removes existing context."""
        context = UserContext(user_id=12345)
        await state_store.upsert_context(context)

        deleted = await state_store.delete_context(12345)
        assert deleted is True

        result = await state_store.get_context(12345)
        assert result is None

    async def test_delete_context_not_found(self, state_store: StateStore) -> None:
        """delete_context returns False when context doesn't exist."""
        deleted = await state_store.delete_context(99999)
        assert deleted is False


@pytest.mark.asyncio
@pytest.mark.unit
class TestProjectCRUD:
    """Tests for Project CRUD operations."""

    async def test_get_project_not_found(self, state_store: StateStore) -> None:
        """get_project returns None when project doesn't exist."""
        result = await state_store.get_project("nonexistent")
        assert result is None

    async def test_upsert_and_get_project(self, state_store: StateStore) -> None:
        """Can create and retrieve project."""
        project = Project(
            name="myproject",
            path="/home/user/myproject",
            description="Test project",
        )
        await state_store.upsert_project(project)

        result = await state_store.get_project("myproject")
        assert result is not None
        assert result.name == "myproject"
        assert result.path == "/home/user/myproject"
        assert result.description == "Test project"

    async def test_upsert_updates_existing_project(self, state_store: StateStore) -> None:
        """upsert_project updates existing project."""
        project1 = Project(name="proj", path="/path1")
        await state_store.upsert_project(project1)

        project2 = Project(name="proj", path="/path2", description="Updated")
        await state_store.upsert_project(project2)

        result = await state_store.get_project("proj")
        assert result is not None
        assert result.path == "/path2"
        assert result.description == "Updated"

    async def test_list_projects_empty(self, state_store: StateStore) -> None:
        """list_projects returns empty list when no projects."""
        result = await state_store.list_projects()
        assert result == []

    async def test_list_projects(self, state_store: StateStore) -> None:
        """list_projects returns all projects sorted by name."""
        await state_store.upsert_project(Project(name="zebra", path="/z"))
        await state_store.upsert_project(Project(name="alpha", path="/a"))
        await state_store.upsert_project(Project(name="middle", path="/m"))

        result = await state_store.list_projects()
        assert len(result) == 3
        assert [p.name for p in result] == ["alpha", "middle", "zebra"]

    async def test_delete_project_success(self, state_store: StateStore) -> None:
        """delete_project removes existing project."""
        await state_store.upsert_project(Project(name="proj", path="/p"))
        deleted = await state_store.delete_project("proj")
        assert deleted is True

        result = await state_store.get_project("proj")
        assert result is None

    async def test_delete_project_not_found(self, state_store: StateStore) -> None:
        """delete_project returns False when project doesn't exist."""
        deleted = await state_store.delete_project("nonexistent")
        assert deleted is False

    async def test_touch_project(self, state_store: StateStore) -> None:
        """touch_project updates last_accessed_at timestamp."""
        project = Project(name="proj", path="/p")
        await state_store.upsert_project(project)

        # Get initial timestamp
        result1 = await state_store.get_project("proj")
        assert result1 is not None
        original_accessed = result1.last_accessed_at

        # Touch the project
        await state_store.touch_project("proj")

        # Verify timestamp updated
        result2 = await state_store.get_project("proj")
        assert result2 is not None
        assert result2.last_accessed_at is not None
        if original_accessed is not None:
            assert result2.last_accessed_at >= original_accessed


@pytest.mark.asyncio
@pytest.mark.unit
class TestRunCRUD:
    """Tests for Run CRUD operations."""

    async def test_create_run_returns_id(self, state_store: StateStore) -> None:
        """create_run returns the new run ID."""
        run = Run(user_id=12345, project_name="proj", command="weld plan")
        run_id = await state_store.create_run(run)
        assert run_id > 0

    async def test_create_and_get_run(self, state_store: StateStore) -> None:
        """Can create and retrieve run."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld plan spec.md",
            status="running",
        )
        run_id = await state_store.create_run(run)

        result = await state_store.get_run(run_id)
        assert result is not None
        assert result.id == run_id
        assert result.user_id == 12345
        assert result.project_name == "proj"
        assert result.command == "weld plan spec.md"
        assert result.status == "running"

    async def test_get_run_not_found(self, state_store: StateStore) -> None:
        """get_run returns None when run doesn't exist."""
        result = await state_store.get_run(99999)
        assert result is None

    async def test_update_run(self, state_store: StateStore) -> None:
        """update_run modifies existing run."""
        run = Run(user_id=12345, project_name="proj", command="cmd")
        run_id = await state_store.create_run(run)
        original_started_at = run.started_at

        # Update run with new started_at (simulating pending -> running transition)
        run.id = run_id
        run.status = "completed"
        run.result = "Success!"
        run.started_at = datetime.now(UTC)
        run.completed_at = datetime.now(UTC)
        updated = await state_store.update_run(run)
        assert updated is True

        result = await state_store.get_run(run_id)
        assert result is not None
        assert result.status == "completed"
        assert result.result == "Success!"
        assert result.completed_at is not None
        # Verify started_at was updated (not the original creation time)
        assert result.started_at >= original_started_at

    async def test_update_run_not_found(self, state_store: StateStore) -> None:
        """update_run returns False when run doesn't exist."""
        run = Run(id=99999, user_id=1, project_name="p", command="c")
        updated = await state_store.update_run(run)
        assert updated is False

    async def test_update_run_requires_id(self, state_store: StateStore) -> None:
        """update_run raises error when run has no ID."""
        run = Run(user_id=1, project_name="p", command="c")
        with pytest.raises(ValueError, match="must have an id"):
            await state_store.update_run(run)

    async def test_list_runs_by_user(self, state_store: StateStore) -> None:
        """list_runs_by_user returns runs for specific user."""
        # Create runs for different users
        await state_store.create_run(Run(user_id=1, project_name="p", command="cmd1"))
        await state_store.create_run(Run(user_id=1, project_name="p", command="cmd2"))
        await state_store.create_run(Run(user_id=2, project_name="p", command="cmd3"))

        runs = await state_store.list_runs_by_user(1)
        assert len(runs) == 2
        assert all(r.user_id == 1 for r in runs)

    async def test_list_runs_by_user_with_status_filter(self, state_store: StateStore) -> None:
        """list_runs_by_user can filter by status."""
        run1 = Run(user_id=1, project_name="p", command="c", status="pending")
        run2 = Run(user_id=1, project_name="p", command="c", status="completed")
        await state_store.create_run(run1)
        await state_store.create_run(run2)

        runs = await state_store.list_runs_by_user(1, status="completed")
        assert len(runs) == 1
        assert runs[0].status == "completed"

    async def test_list_runs_by_user_respects_limit(self, state_store: StateStore) -> None:
        """list_runs_by_user respects limit parameter."""
        for i in range(5):
            await state_store.create_run(Run(user_id=1, project_name="p", command=f"cmd{i}"))

        runs = await state_store.list_runs_by_user(1, limit=3)
        assert len(runs) == 3

    async def test_list_runs_by_project(self, state_store: StateStore) -> None:
        """list_runs_by_project returns runs for specific project."""
        await state_store.create_run(Run(user_id=1, project_name="proj1", command="c"))
        await state_store.create_run(Run(user_id=2, project_name="proj1", command="c"))
        await state_store.create_run(Run(user_id=1, project_name="proj2", command="c"))

        runs = await state_store.list_runs_by_project("proj1")
        assert len(runs) == 2
        assert all(r.project_name == "proj1" for r in runs)


@pytest.mark.asyncio
@pytest.mark.unit
class TestStateStoreErrors:
    """Tests for StateStore error handling."""

    async def test_operations_fail_without_init(self) -> None:
        """Operations should fail if init() not called."""
        store = StateStore(":memory:")
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.get_context(12345)

    async def test_file_based_db_creates_parent_dirs(self, tmp_path) -> None:
        """File-based database creates parent directories."""
        db_path = tmp_path / "nested" / "dir" / "state.db"
        async with StateStore(db_path) as store:
            await store.upsert_context(UserContext(user_id=1))

        assert db_path.exists()


@pytest.mark.asyncio
@pytest.mark.unit
class TestMarkOrphanedRunsFailed:
    """Tests for mark_orphaned_runs_failed startup housekeeping."""

    async def test_marks_running_runs_as_failed(self, state_store: StateStore) -> None:
        """Running runs should be marked as failed."""
        run = Run(user_id=1, project_name="proj", command="cmd", status="running")
        run_id = await state_store.create_run(run)

        count = await state_store.mark_orphaned_runs_failed()

        assert count == 1
        result = await state_store.get_run(run_id)
        assert result is not None
        assert result.status == "failed"
        assert result.error == "Bot restarted during execution"
        assert result.completed_at is not None

    async def test_marks_pending_runs_as_failed(self, state_store: StateStore) -> None:
        """Pending runs should be marked as failed."""
        run = Run(user_id=1, project_name="proj", command="cmd", status="pending")
        run_id = await state_store.create_run(run)

        count = await state_store.mark_orphaned_runs_failed()

        assert count == 1
        result = await state_store.get_run(run_id)
        assert result is not None
        assert result.status == "failed"

    async def test_leaves_completed_runs_unchanged(self, state_store: StateStore) -> None:
        """Completed runs should not be affected."""
        run = Run(user_id=1, project_name="proj", command="cmd", status="completed")
        run_id = await state_store.create_run(run)

        count = await state_store.mark_orphaned_runs_failed()

        assert count == 0
        result = await state_store.get_run(run_id)
        assert result is not None
        assert result.status == "completed"

    async def test_leaves_failed_runs_unchanged(self, state_store: StateStore) -> None:
        """Already-failed runs should not be affected."""
        run = Run(
            user_id=1, project_name="proj", command="cmd", status="failed", error="Original error"
        )
        run_id = await state_store.create_run(run)

        count = await state_store.mark_orphaned_runs_failed()

        assert count == 0
        result = await state_store.get_run(run_id)
        assert result is not None
        assert result.error == "Original error"

    async def test_marks_multiple_orphaned_runs(self, state_store: StateStore) -> None:
        """Multiple orphaned runs should all be marked."""
        await state_store.create_run(
            Run(user_id=1, project_name="p", command="c", status="running")
        )
        await state_store.create_run(
            Run(user_id=2, project_name="p", command="c", status="pending")
        )
        await state_store.create_run(
            Run(user_id=3, project_name="p", command="c", status="running")
        )
        await state_store.create_run(
            Run(user_id=4, project_name="p", command="c", status="completed")
        )

        count = await state_store.mark_orphaned_runs_failed()

        assert count == 3

    async def test_returns_zero_when_no_orphans(self, state_store: StateStore) -> None:
        """Returns 0 when no orphaned runs exist."""
        await state_store.create_run(
            Run(user_id=1, project_name="p", command="c", status="completed")
        )
        await state_store.create_run(Run(user_id=2, project_name="p", command="c", status="failed"))

        count = await state_store.mark_orphaned_runs_failed()

        assert count == 0


@pytest.mark.asyncio
@pytest.mark.unit
class TestPruneOldRuns:
    """Tests for prune_old_runs startup housekeeping."""

    async def test_prunes_runs_exceeding_limit(self, state_store: StateStore) -> None:
        """Runs exceeding the limit per user should be deleted."""
        # Create 5 runs for user 1
        for i in range(5):
            await state_store.create_run(Run(user_id=1, project_name="p", command=f"cmd{i}"))

        count = await state_store.prune_old_runs(keep_per_user=3)

        assert count == 2
        runs = await state_store.list_runs_by_user(1)
        assert len(runs) == 3

    async def test_keeps_most_recent_runs(self, state_store: StateStore) -> None:
        """The most recent runs (by ID) should be kept."""
        run_ids = []
        for i in range(5):
            run_id = await state_store.create_run(
                Run(user_id=1, project_name="p", command=f"cmd{i}")
            )
            run_ids.append(run_id)

        await state_store.prune_old_runs(keep_per_user=3)

        # Only the last 3 runs should remain
        runs = await state_store.list_runs_by_user(1)
        remaining_ids = [r.id for r in runs if r.id is not None]
        assert sorted(remaining_ids) == sorted(run_ids[-3:])

    async def test_prunes_per_user_independently(self, state_store: StateStore) -> None:
        """Each user's runs should be pruned independently."""
        # Create 4 runs for user 1 and 3 runs for user 2
        for i in range(4):
            await state_store.create_run(Run(user_id=1, project_name="p", command=f"u1cmd{i}"))
        for i in range(3):
            await state_store.create_run(Run(user_id=2, project_name="p", command=f"u2cmd{i}"))

        count = await state_store.prune_old_runs(keep_per_user=2)

        # User 1 should have 2 runs deleted (4 - 2 = 2)
        # User 2 should have 1 run deleted (3 - 2 = 1)
        assert count == 3

        runs_user1 = await state_store.list_runs_by_user(1)
        runs_user2 = await state_store.list_runs_by_user(2)
        assert len(runs_user1) == 2
        assert len(runs_user2) == 2

    async def test_no_pruning_under_limit(self, state_store: StateStore) -> None:
        """No runs deleted if under the limit."""
        for i in range(3):
            await state_store.create_run(Run(user_id=1, project_name="p", command=f"cmd{i}"))

        count = await state_store.prune_old_runs(keep_per_user=5)

        assert count == 0
        runs = await state_store.list_runs_by_user(1)
        assert len(runs) == 3

    async def test_returns_zero_when_no_runs(self, state_store: StateStore) -> None:
        """Returns 0 when no runs exist."""
        count = await state_store.prune_old_runs(keep_per_user=10)
        assert count == 0

    async def test_default_keep_per_user_is_100(self, state_store: StateStore) -> None:
        """Default keep_per_user should be 100."""
        # Create 5 runs (well under 100)
        for i in range(5):
            await state_store.create_run(Run(user_id=1, project_name="p", command=f"cmd{i}"))

        count = await state_store.prune_old_runs()  # Uses default

        assert count == 0


@pytest.mark.asyncio
@pytest.mark.unit
class TestSyncProjectsFromConfig:
    """Tests for sync_projects_from_config startup housekeeping."""

    async def test_adds_new_projects(self, state_store: StateStore, tmp_path: Path) -> None:
        """Projects in config but not in DB should be added."""
        # Create real directories for path resolution
        proj_path = tmp_path / "myproject"
        proj_path.mkdir()

        config = TelegramConfig(
            bot_token="token",
            projects=[TelegramProject(name="myproject", path=proj_path, description="Test proj")],
        )

        result = await state_store.sync_projects_from_config(config)

        assert result["added"] == 1
        assert result["updated"] == 0
        assert result["removed"] == 0
        assert result["skipped"] == 0

        project = await state_store.get_project("myproject")
        assert project is not None
        assert project.path == str(proj_path.resolve())
        assert project.description == "Test proj"

    async def test_updates_existing_projects(self, state_store: StateStore, tmp_path: Path) -> None:
        """Projects in both config and DB should be updated."""
        proj_path = tmp_path / "proj"
        proj_path.mkdir()

        # Add existing project to DB
        await state_store.upsert_project(
            Project(name="proj", path="/old/path", description="Old desc")
        )
        # Touch to set last_accessed_at
        await state_store.touch_project("proj")
        existing = await state_store.get_project("proj")
        original_accessed_at = existing.last_accessed_at if existing else None

        # Config has updated path/description
        config = TelegramConfig(
            bot_token="token",
            projects=[TelegramProject(name="proj", path=proj_path, description="New desc")],
        )

        result = await state_store.sync_projects_from_config(config)

        assert result["updated"] == 1
        assert result["added"] == 0

        project = await state_store.get_project("proj")
        assert project is not None
        assert project.path == str(proj_path.resolve())
        assert project.description == "New desc"
        # last_accessed_at should be preserved
        assert project.last_accessed_at == original_accessed_at

    async def test_removes_projects_not_in_config(
        self, state_store: StateStore, tmp_path: Path
    ) -> None:
        """Projects in DB but not in config should be removed."""
        # Add project to DB that won't be in config
        await state_store.upsert_project(Project(name="old_proj", path="/old"))

        proj_path = tmp_path / "new_proj"
        proj_path.mkdir()
        config = TelegramConfig(
            bot_token="token",
            projects=[TelegramProject(name="new_proj", path=proj_path)],
        )

        result = await state_store.sync_projects_from_config(config)

        assert result["removed"] == 1
        assert result["added"] == 1

        # old_proj should be gone
        assert await state_store.get_project("old_proj") is None
        # new_proj should exist
        assert await state_store.get_project("new_proj") is not None

    async def test_skips_removal_with_active_runs(
        self, state_store: StateStore, tmp_path: Path
    ) -> None:
        """Projects with active runs should not be removed."""
        # Add project to DB with an active run
        await state_store.upsert_project(Project(name="active_proj", path="/active"))
        await state_store.create_run(
            Run(user_id=1, project_name="active_proj", command="cmd", status="running")
        )

        proj_path = tmp_path / "new_proj"
        proj_path.mkdir()
        config = TelegramConfig(
            bot_token="token",
            projects=[TelegramProject(name="new_proj", path=proj_path)],
        )

        result = await state_store.sync_projects_from_config(config)

        assert result["skipped"] == 1
        assert result["removed"] == 0

        # active_proj should still exist
        assert await state_store.get_project("active_proj") is not None

    async def test_skips_removal_with_pending_runs(
        self, state_store: StateStore, tmp_path: Path
    ) -> None:
        """Projects with pending runs should not be removed."""
        await state_store.upsert_project(Project(name="pending_proj", path="/pending"))
        await state_store.create_run(
            Run(user_id=1, project_name="pending_proj", command="cmd", status="pending")
        )

        proj_path = tmp_path / "new_proj"
        proj_path.mkdir()
        config = TelegramConfig(
            bot_token="token",
            projects=[TelegramProject(name="new_proj", path=proj_path)],
        )

        result = await state_store.sync_projects_from_config(config)

        assert result["skipped"] == 1
        assert await state_store.get_project("pending_proj") is not None

    async def test_removes_with_completed_runs(
        self, state_store: StateStore, tmp_path: Path
    ) -> None:
        """Projects with only completed/failed runs can be removed."""
        await state_store.upsert_project(Project(name="old_proj", path="/old"))
        await state_store.create_run(
            Run(user_id=1, project_name="old_proj", command="cmd", status="completed")
        )
        await state_store.create_run(
            Run(user_id=2, project_name="old_proj", command="cmd2", status="failed")
        )

        proj_path = tmp_path / "new_proj"
        proj_path.mkdir()
        config = TelegramConfig(
            bot_token="token",
            projects=[TelegramProject(name="new_proj", path=proj_path)],
        )

        result = await state_store.sync_projects_from_config(config)

        assert result["removed"] == 1
        assert result["skipped"] == 0
        assert await state_store.get_project("old_proj") is None

    async def test_empty_config_removes_all_projects(self, state_store: StateStore) -> None:
        """Empty config should remove all projects without active runs."""
        await state_store.upsert_project(Project(name="proj1", path="/p1"))
        await state_store.upsert_project(Project(name="proj2", path="/p2"))

        config = TelegramConfig(bot_token="token", projects=[])

        result = await state_store.sync_projects_from_config(config)

        assert result["removed"] == 2
        projects = await state_store.list_projects()
        assert len(projects) == 0

    async def test_handles_multiple_projects(self, state_store: StateStore, tmp_path: Path) -> None:
        """Handles mix of adds, updates, and removes."""
        # Existing: proj1 (will be updated), proj2 (will be removed)
        await state_store.upsert_project(Project(name="proj1", path="/old1"))
        await state_store.upsert_project(Project(name="proj2", path="/old2"))

        # Config: proj1 (update), proj3 (add)
        path1 = tmp_path / "proj1"
        path3 = tmp_path / "proj3"
        path1.mkdir()
        path3.mkdir()

        config = TelegramConfig(
            bot_token="token",
            projects=[
                TelegramProject(name="proj1", path=path1, description="Updated"),
                TelegramProject(name="proj3", path=path3, description="New"),
            ],
        )

        result = await state_store.sync_projects_from_config(config)

        assert result["added"] == 1
        assert result["updated"] == 1
        assert result["removed"] == 1
        assert result["skipped"] == 0

        projects = await state_store.list_projects()
        project_names = [p.name for p in projects]
        assert sorted(project_names) == ["proj1", "proj3"]
