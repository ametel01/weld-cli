# Research Findings: Telegram Bot Integration for weld-cli

## Authoritative Files

| Concept | Authoritative File(s) |
|---------|----------------------|
| CLI Structure | `src/weld/cli.py` |
| Output Formatting | `src/weld/output.py` |
| Configuration | `src/weld/config.py` |
| Git Operations | `src/weld/services/git.py` |
| Claude Integration | `src/weld/services/claude.py` |
| Session Detection | `src/weld/services/session_detector.py` |
| Session Tracking | `src/weld/services/session_tracker.py` |
| Session Models | `src/weld/models/session.py` |
| Transcript Rendering | `src/weld/services/transcript_renderer.py` |
| Gist Upload | `src/weld/services/gist_uploader.py` |
| Plan Parsing | `src/weld/core/plan_parser.py` |
| Implement Command | `src/weld/commands/implement.py` |
| Commit Command | `src/weld/commands/commit.py` |
| History Tracking | `src/weld/core/history.py` |
| Timeouts/Constants | `src/weld/constants.py` |

---

## Key Findings

### Q1: How should the Telegram module integrate with existing CLI structure?

**Answer:** Create a sub-app registered via `app.add_typer()` in `cli.py`, following the `discover` pattern.

**Evidence:** `cli.py:45` - `app.add_typer(discover_app, name="discover")` shows sub-command group pattern.

**Integration Pattern:**
```python
# In cli.py
from weld.telegram.cli import telegram_app
app.add_typer(telegram_app, name="telegram")
```

**Proposed Layout:**
```
src/weld/
  telegram/
    __init__.py
    cli.py           # Typer sub-app: init, serve, projects, whoami, doctor, run
    bot.py           # Telegram update handling + routing
    config.py        # TelegramConfig schema + load/save
    auth.py          # Allowlists, optional auth, rate limiting
    runner.py        # Subprocess execution + streaming
    queue.py         # Per-context queue/locks
    state.py         # State store (sqlite or json)
    worktrees.py     # Worktree management
    files.py         # Fetch/push helpers + path validation
    format.py        # Telegram message formatting + chunking
```

**Confidence:** High

---

### Q2: Telegram Library Choice - python-telegram-bot vs aiogram

**Answer:** Use **aiogram 3.x** for better async performance and streaming support.

**Evidence:** Web research shows aiogram is built async-first, offers better throughput for real-time streaming, and scales better under load.

**Rationale:**
1. **Streaming requirement**: Weld needs real-time output streaming (`STDOUT_CHUNK`, `STDERR_CHUNK` events). Aiogram's native async/await patterns align with `asyncio.subprocess` for non-blocking reads.
2. **Performance**: Aiogram handles concurrent connections better - important when multiple runs stream simultaneously.
3. **Existing async patterns**: `services/claude.py:run_claude()` already uses `subprocess.Popen` with `select()` for timeout-aware streaming - easy to port to `asyncio.subprocess`.
4. **State management**: Aiogram has built-in FSM (Finite State Machine) for conversation state.

**Tradeoffs:**
- Steeper learning curve (requires asyncio familiarity)
- Less beginner-friendly documentation
- Weld codebase is currently sync - will need async bridge in `runner.py`

**Version:** aiogram 3.22+ (Python 3.10+)

**Confidence:** High

---

### Q3: State Store Choice - SQLite vs JSON

**Answer:** Use **SQLite** for primary state, **JSONL** for history logs (matching existing patterns).

**Evidence:**
- `.weld/sessions/registry.jsonl` uses JSONL for append-only session logs (`session_tracker.py:109`)
- `.weld/{command}/history.jsonl` uses JSONL for command history (`history.py:47`)
- SQLite provides transactions, indexing, and concurrent access safety for mutable state

**State Store Architecture:**

| Data Type | Storage | Rationale |
|-----------|---------|-----------|
| Chat contexts | SQLite | Mutable, queried by chat_id |
| Project registry | SQLite | CRUD operations |
| Run history | SQLite | Complex queries (last 5, by status) |
| Run logs | JSONL | Append-only, per-run log streaming |
| Message IDs | SQLite | Mutable (edited messages) |

**SQLite Location:** `~/.weld/telegram/state.db`
**Runs Log Location:** `~/.weld/telegram/runs/{run_id}.jsonl`

**Schema (sqlite):**
```sql
-- Chat context (active project/branch per chat)
CREATE TABLE contexts (
    chat_id INTEGER PRIMARY KEY,
    project_name TEXT NOT NULL,
    branch TEXT,
    updated_at TIMESTAMP
);

-- Registered projects
CREATE TABLE projects (
    name TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    default_branch TEXT,
    worktrees_enabled BOOLEAN DEFAULT FALSE
);

-- Run history
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    project_name TEXT NOT NULL,
    branch TEXT,
    command TEXT NOT NULL,
    status TEXT NOT NULL,  -- QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELED
    created_at TIMESTAMP,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    exit_code INTEGER,
    header_message_id INTEGER,  -- For editing status
    summary TEXT  -- Last 50 lines
);
```

**Confidence:** High

---

### Q4: How to detect Weld "phases" reliably?

**Answer:** Parse structured markers from weld command output OR add `--json-events` flag.

**Evidence:**
- `plan_parser.py:14-15` defines phase patterns: `^## Phase (\d+):\s*(.+?)`
- `implement.py:147` marks completion with `**COMPLETE**` suffix
- Claude streaming uses `--output-format stream-json` (`claude.py:68`)

**Current Detection Options:**
1. **Regex parsing**: Parse `## Phase N:` markers from stdout
2. **Step completion**: Watch for `**COMPLETE**` in output
3. **Exit code**: 0 = success, non-zero = failure

**Recommended Enhancement (v2):**
Add `--emit-events` flag to weld commands that outputs JSONL events:
```json
{"type": "phase_started", "phase": 1, "title": "Setup", "ts": "..."}
{"type": "step_completed", "phase": 1, "step": 2, "ts": "..."}
{"type": "run_finished", "exit_code": 0, "ts": "..."}
```

**MVP Approach:** Parse stdout for `## Phase` and `### Step` markers, track `**COMPLETE**` for progress.

**Confidence:** Medium (regex parsing is fragile; structured events recommended for v2)

---

### Q5: Should group topics be first-class "contexts"?

**Answer:** **No for v1**. Support group chats but not topic-based threading.

**Evidence:**
- SPEC.md §1.1: "Topic-based group (optional v2)"
- MVP scope focused on DMs and basic group chats
- Topic threading adds complexity (separate context per topic)

**Implementation:**
- Use `chat_id` as context key (same for DM and group)
- Ignore `message_thread_id` in v1
- Design state schema to support topic threading later:
  ```sql
  -- Future: composite key (chat_id, thread_id)
  contexts (chat_id, thread_id, project_name, ...)
  ```

**Confidence:** High

---

### Q6: Plugin surface for Telegram integration?

**Answer:** **No for v1**. Not needed for weld's constrained command set.

**Evidence:**
- SPEC.md §5 mentions Takopi's plugins but marks as non-goal
- Weld allowlist is fixed: `doctor`, `plan`, `interview`, `implement`, `commit`
- Plugin system adds maintenance burden with no v1 use case

**Design for extensibility:**
- Use command registry pattern in `bot.py`
- Commands defined as handler functions, easily addable later
- No formal plugin API until clear use case emerges

**Confidence:** High

---

## Actual Flows

### Flow: Telegram Command Execution

1. `bot.py` - Telegram update received via polling
2. `bot.py:route_message()` - Parse command, validate allowlist
3. `auth.py:check_auth()` - Verify chat_id, user_id in allowlist
4. `queue.py:enqueue_run()` - Add to per-context queue
5. `runner.py:execute_run()` - Spawn subprocess:
   ```python
   asyncio.create_subprocess_exec(
       "weld", *args,
       cwd=repo_path,
       stdout=asyncio.subprocess.PIPE,
       stderr=asyncio.subprocess.PIPE
   )
   ```
6. `runner.py:stream_output()` - Async read stdout/stderr
7. `format.py:format_chunk()` - Chunk for Telegram (4KB limit)
8. `bot.py:send_or_edit()` - Send/edit Telegram message
9. `state.py:update_run()` - Update run status in SQLite

### Flow: Session-Based Commit (from weld commit)

1. `commit.py:commit()` - Entry point
2. `session_tracker.py:SessionRegistry` - Load `.weld/sessions/registry.jsonl`
3. `session_tracker.py:resolve_files_to_sessions()` - Map staged files to sessions
4. `transcript_renderer.py:render_transcript()` - Parse session JSONL, redact secrets
5. `gist_uploader.py:upload_gist()` - `gh gist create` via subprocess
6. `git.py:commit_file()` - Create commit with gist trailer

---

## Verified Facts

- Subprocess calls never use `shell=True` (`git.py:27`, `claude.py:75`)
- All subprocess calls have timeout parameter (`constants.py:4-8`)
- Config file at `.weld/config.toml` using TOML/Pydantic (`config.py:58`)
- Session registry at `.weld/sessions/registry.jsonl` (`session_tracker.py:109`)
- History logs at `.weld/{command}/history.jsonl` (`history.py:47`)
- Claude streaming uses `--output-format stream-json` (`claude.py:68`)
- Transcript redaction patterns defined in `transcript_renderer.py:14-25`
- GIT_TIMEOUT = 30s, CLAUDE_TIMEOUT = 1800s (`constants.py:4-5`)
- OutputContext supports json_mode and dry_run (`output.py:17-19`)

---

## Corrections

- **SPEC assumption**: "State store: sqlite or single JSON file"
  → **Actual pattern**: Use SQLite for mutable state, JSONL for append-only logs (matching existing `.weld/sessions/` pattern)

- **SPEC assumption**: Streaming "throttle: at most once per 2 seconds or per 4KB"
  → **Existing pattern**: `claude.py` streams line-by-line without throttle; throttling should be in `format.py` for Telegram limits

---

## Unknowns

- **Worktree lock mechanism**: SPEC mentions "lock: only one run per worktree at a time" but no existing lock implementation in codebase. Need to implement file-based or SQLite-based locking.

- **Telegram rate limits**: Unknown how aggressive Telegram's rate limits are for message editing. May need adaptive throttling.

- **Resume semantics**: SPEC references Takopi's "reply to continue" but exact UX for context restoration needs design work.

---

## Requirements Summary (MVP)

### Telegram Commands (Safe Mode)
| Telegram | Weld CLI |
|----------|----------|
| `/doctor` | `weld doctor` |
| `/plan <spec> [-o <out>]` | `weld plan <spec> -o <out>` |
| `/interview <spec> [-o <out>]` | `weld interview <spec> -o <out>` |
| `/implement <plan>` | `weld implement <plan>` |
| `/commit [--all]` | `weld commit [--all]` |
| `/status` | (internal) |
| `/cancel` | (internal) |

### CLI Commands
| Command | Purpose |
|---------|---------|
| `weld telegram init` | Interactive setup wizard |
| `weld telegram serve` | Run bot server (polling) |
| `weld telegram projects add <name> <path>` | Register project |
| `weld telegram projects remove <name>` | Unregister project |
| `weld telegram projects list` | List registered projects |
| `weld telegram whoami` | Show auth status |
| `weld telegram doctor` | Validate telegram setup |

### Security Requirements
- Allowlist chat_id and user_id enforcement
- No `shell=True` in subprocess calls
- Path validation: no `..` traversal, resolve symlinks
- Bot token never logged (use `WELD_TELEGRAM_TOKEN` env)
- Config file permissions `0600`

### Dependencies
```toml
[project.optional-dependencies]
telegram = [
    "aiogram>=3.22",
    "aiosqlite>=0.19.0",  # Async SQLite
]
```

---

## References

- [aiogram GitHub](https://github.com/aiogram/aiogram) - Async Telegram framework
- [python-telegram-bot vs aiogram](https://www.restack.io/p/best-telegram-bot-frameworks-ai-answer-python-telegram-bot-vs-aiogram-cat-ai) - Comparison
- [Takopi](https://github.com/banteg/takopi) - Reference implementation for Telegram CLI bridge
- [SQLite vs JSON](https://pl-rants.net/posts/when-not-json/) - State storage patterns
