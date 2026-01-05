# Run Locking Implementation Review

Review of Step 1.2 (Run Locking) implementation.

## Critical Bugs

### 1. Lock Released Immediately After `run_start` Returns

**Location:** `src/weld/commands/run.py:51-88`

The lock is acquired and released entirely within `run_start`. Since the function only creates the run directory and generates the plan prompt (setup work), the lock is released before any actual concurrent-sensitive operations occur.

```python
try:
    acquire_lock(weld_dir, run_id, f"run --spec {spec}")
except LockError as e:
    ...
try:
    # ... setup work ...
finally:
    release_lock(weld_dir)  # Released immediately!
```

The actual operations (`plan import`, `step loop`, `commit`) that modify run state are **not protected** by any lock.

---

### 2. Missing Lock Acquisition in Other Commands

These commands all modify run state but have **no locking**:

| Command | File | Writes to |
|---------|------|-----------|
| `plan import` | `plan.py:16` | `plan/output.md`, `plan/plan.raw.md`, `meta.json` |
| `plan review` | `plan.py:64` | `plan/codex.prompt.md`, `plan/codex.output.md`, `plan/plan.final.md` |
| `step select` | `step.py:27` | `steps/<n>/step.json`, `prompt/impl.prompt.md` |
| `step loop` | `step.py:251` | Entire `iter/` directory tree |
| `step snapshot` | `step.py:85` | `iter/<n>/diff.patch`, `status.json`, `checks*.json` |
| `commit` | `commit.py:50` | `meta.json`, creates git commits |

---

### 3. Race Condition (TOCTOU) in `acquire_lock`

**Location:** `src/weld/core/lock_manager.py:77-112`

Time-of-check-to-time-of-use vulnerability:

```python
existing = get_current_lock(weld_dir)  # Check
if existing:
    if is_stale_lock(existing):
        lock_path.unlink()
    elif existing.pid != os.getpid():
        raise LockError(...)
# Gap where another process could also check
lock_path.write_text(...)  # Use
```

Two processes could both see no lock and both write simultaneously.

**Mitigation options:**
- Use atomic file creation with `O_CREAT | O_EXCL` flags
- Use `fcntl.flock()` for advisory locking
- Use a lock directory instead of file (mkdir is atomic)

---

## Test Gaps

### 4. Test `test_acquire_fails_if_locked_by_other` Doesn't Test Lock Failure

**Location:** `tests/test_lock_manager.py:37-51`

```python
def test_acquire_fails_if_locked_by_other(self, weld_dir: Path) -> None:
    fake_lock = Lock(pid=99999, ...)  # PID 99999 is likely dead
    ...
    lock = acquire_lock(weld_dir, "new-run", "new command")
    assert lock.run_id == "new-run"  # Asserts SUCCESS, not failure!
```

This test passes because PID 99999 is not running (stale). **No test verifies `LockError` is raised.**

**Fix:** Use current process PID to simulate active lock:

```python
def test_acquire_fails_if_locked_by_other(self, weld_dir: Path) -> None:
    # Simulate lock held by "another" process by using a running PID
    # We use PID 1 (init) which is always running on Unix systems
    fake_lock = Lock(pid=1, run_id="other", command="other")
    (weld_dir / "active.lock").write_text(fake_lock.model_dump_json())

    with pytest.raises(LockError, match="Run already in progress"):
        acquire_lock(weld_dir, "new-run", "new command")
```

---

## Implementation Gaps

### 5. `update_heartbeat` Is Never Called

**Location:** `src/weld/core/lock_manager.py:128`

The function exists but is never invoked anywhere in the codebase. Long-running operations (`step loop` can take minutes/hours) will have stale locks after the 1-hour timeout, potentially allowing concurrent access.

**Required:** Call `update_heartbeat()` periodically in `step loop` and other long operations.

---

### 6. `update_heartbeat` Not Exported

**Location:** `src/weld/core/__init__.py`

The function is not exported from the core module, so commands cannot use it even if they wanted to.

---

## Minor Issues

### 7. Unnecessary `pass` in Exception Class

**Location:** `src/weld/core/lock_manager.py:17-20`

```python
class LockError(Exception):
    """Error acquiring or managing lock."""
    pass  # Unnecessary, docstring serves as body
```

---

## Summary

| Issue | Severity | Location |
|-------|----------|----------|
| Lock released after setup only | Critical | `commands/run.py:88` |
| No locking in plan/step/commit commands | Critical | `commands/*.py` |
| TOCTOU race in acquire_lock | Critical | `lock_manager.py:92-111` |
| Test doesn't verify LockError raised | Test Gap | `test_lock_manager.py:37` |
| `update_heartbeat` never called | Gap | `lock_manager.py:128` |
| `update_heartbeat` not exported | Gap | `core/__init__.py` |
| Redundant `pass` | Style | `lock_manager.py:20` |

## Recommended Fix Priority

1. **Add locking to `step loop`** - This is the primary concurrent-access risk
2. **Fix the TOCTOU race** - Use atomic file creation
3. **Add test for actual lock conflict** - Use PID 1 or mock `_is_pid_running`
4. **Integrate heartbeat updates** - Call in long-running loops
5. **Consider removing lock from `run_start`** - Setup is fast and idempotent
