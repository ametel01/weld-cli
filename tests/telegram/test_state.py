"""Tests for Telegram bot state store."""

from datetime import UTC, datetime

import pytest

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

        # Update run
        run.id = run_id
        run.status = "completed"
        run.result = "Success!"
        run.completed_at = datetime.now(UTC)
        updated = await state_store.update_run(run)
        assert updated is True

        result = await state_store.get_run(run_id)
        assert result is not None
        assert result.status == "completed"
        assert result.result == "Success!"
        assert result.completed_at is not None

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
