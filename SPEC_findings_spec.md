# Spec: Telegram Bot Integration for weld-cli

## Summary

A Telegram bot interface for weld-cli that enables remote execution of weld commands (doctor, plan, interview, implement, commit) with real-time output streaming. Users interact via Telegram messages, with FIFO queuing per chat and SQLite-backed state management.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Telegram library | aiogram 3.x | Async-first, better streaming support, built-in FSM |
| State storage | SQLite (mutable) + JSONL (logs) | Matches existing weld patterns |
| Bot token | ENV variable only (`WELD_TELEGRAM_TOKEN`) | Simple, no secret storage in config files |
| Output streaming | Edit single message | Clean UX, shows latest 4KB, avoids message spam |
| Concurrency | Queue (FIFO) per chat | One run at a time, additional runs queued |
| Cancel mechanism | SIGTERM + 5s grace → SIGKILL | Graceful shutdown with fallback |
| Project switching | Explicit `/use <project>` | Clear context, no ambiguity |
| Worktree locking | SQLite row lock | Uses existing DB, simple, atomic |
| File operations | MVP includes /fetch and /push | Full remote workflow support |
| Error display | Inline in message | Single message shows ❌ FAILED + exit code + stderr |
| UI | Text commands only | No inline buttons, keep it simple |
| Large files | Upload to gist | Works for any text file, sends link |
| Push validation | Path allowlist per project | Configurable safe directories |
| Edit throttling | 2 seconds minimum | Balance responsiveness vs rate limits |
| Auth model | User-level allowlist | user_id check only, works in any chat |
| Empty state | Block all commands | Explicit project registration required |

## Requirements

### Must Have

- [ ] `weld telegram init` - Interactive setup wizard (sets env var reminder, validates token)
- [ ] `weld telegram serve` - Run bot server (long-polling mode)
- [ ] `weld telegram projects add/remove/list` - Project registry management
- [ ] `weld telegram whoami` - Show current auth status
- [ ] `weld telegram doctor` - Validate telegram setup (token, deps, projects)
- [ ] Bot commands: `/doctor`, `/plan`, `/interview`, `/implement`, `/commit`
- [ ] Bot commands: `/use <project>`, `/status`, `/cancel`
- [ ] Bot commands: `/fetch <path>`, `/push` (file upload via Telegram)
- [ ] Real-time output streaming with 2s edit throttle
- [ ] FIFO queue per chat with queue position feedback
- [ ] SQLite state store at `~/.weld/telegram/state.db`
- [ ] Run logs at `~/.weld/telegram/runs/{run_id}.jsonl`
- [ ] User allowlist enforcement

### Must Not

- [ ] Store bot token in config files (env only)
- [ ] Use `shell=True` in subprocess calls
- [ ] Allow path traversal (`..`) in file operations
- [ ] Skip timeout on subprocess calls
- [ ] Log bot token or user tokens
- [ ] Allow pushing to arbitrary paths (allowlist enforced)

## Behavior

### `/use <project>` - Switch Context

- Input: Project name registered via `weld telegram projects add`
- Output: "Switched to project: myproject (branch: main)"
- Errors: "Project not found. Available: proj1, proj2" if unknown

### `/doctor`, `/plan`, `/interview`, `/implement`, `/commit` - Run Commands

- Input: Command + args (e.g., `/implement plan.md`)
- Output: Streaming output in single message, edited every 2s max
- Progress: Message shows "⏳ Running..." then final status
- Completion: "✅ SUCCEEDED (exit 0)" or "❌ FAILED (exit 1)\n```\n<last stderr>\n```"
- Queue: If run already active, "Queued at position #2. /cancel to abort."

### `/cancel` - Abort Active Run

- Input: None (cancels current chat's active run)
- Output: "Canceling run abc123..."
- Behavior: SIGTERM → wait 5s → SIGKILL if needed
- Completion: "Run canceled."
- Errors: "No active run to cancel."

### `/status` - Show Current State

- Input: None
- Output: Active run status, queue depth, current project/branch
- Example: "Project: myproject (main)\nActive: /implement plan.md (running 45s)\nQueue: 1 pending"

### `/fetch <path>` - Download File

- Input: Relative path within project
- Output: File sent as Telegram document
- Large files (>20MB): Upload to GitHub Gist, send link
- Errors: "File not found" or "Path not allowed"

### `/push` - Upload File

- Input: Reply to a Telegram document + target path
- Validation: Path must be in project's push_paths allowlist
- Output: "File saved to specs/feature.md"
- Errors: "Path not in allowlist. Allowed: specs/, plans/"

### Edge Cases

| Case | Behavior |
|------|----------|
| Unknown command | "Unknown command. Try /help" |
| No project selected | "No project selected. Use /use <project> first." |
| Project not registered | "Project 'foo' not found. Available: bar, baz" |
| Unauthorized user | Silent ignore (no response) |
| Rate limited by Telegram | Exponential backoff on edits |
| Bot token invalid | `weld telegram serve` exits with error |
| Run timeout (30min) | Auto-cancel with timeout message |
| Empty queue | `/status` shows "Queue: empty" |
| Concurrent /cancel | First wins, second gets "No active run" |

## Technical Notes

### File Structure

```
src/weld/telegram/
  __init__.py
  cli.py           # Typer sub-app: init, serve, projects, whoami, doctor
  bot.py           # Telegram update handler + command routing
  config.py        # TelegramConfig schema (project registry, allowlist)
  auth.py          # User allowlist check
  runner.py        # Subprocess execution with async streaming
  queue.py         # Per-chat FIFO queue with asyncio.Queue
  state.py         # SQLite wrapper (aiosqlite)
  files.py         # /fetch and /push handlers with path validation
  format.py        # Telegram message formatting + 4KB chunking
```

### SQLite Schema

```sql
CREATE TABLE contexts (
    chat_id INTEGER PRIMARY KEY,
    project_name TEXT NOT NULL,
    branch TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE projects (
    name TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    default_branch TEXT,
    push_paths TEXT  -- JSON array of allowed push paths
);

CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    project_name TEXT NOT NULL,
    branch TEXT,
    command TEXT NOT NULL,
    status TEXT NOT NULL,  -- QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    exit_code INTEGER,
    message_id INTEGER,  -- For editing status
    error_summary TEXT
);

CREATE INDEX idx_runs_chat_status ON runs(chat_id, status);
```

### Locking Strategy

Row-level lock in SQLite via status check:
```python
# Before starting run:
UPDATE runs SET status = 'RUNNING', started_at = ?
WHERE run_id = ? AND status = 'QUEUED'
# Check rowcount == 1 to confirm lock acquired
```

### Dependencies

```toml
[project.optional-dependencies]
telegram = [
    "aiogram>=3.22",
    "aiosqlite>=0.19.0",
]
```

### Config File (projects only, no token)

Location: `~/.weld/telegram/config.toml`
```toml
[[projects]]
name = "myproject"
path = "/home/user/code/myproject"
default_branch = "main"
push_paths = ["specs/", "plans/"]

[auth]
allowed_users = [123456789, 987654321]
```

## Open Questions

- Telegram rate limits: Exact limits for message editing unknown. May need adaptive throttling if 2s proves insufficient.
- Webhook vs polling: MVP uses polling. Webhook mode could be added later for production deployments.

## Out of Scope

- Topic-based threading (group topics) - deferred to v2
- Plugin system for extensibility - no clear use case yet
- Inline keyboard buttons - text-only for simplicity
- Webhook mode - polling sufficient for MVP
- Multi-user concurrent runs in same chat - one queue per chat
