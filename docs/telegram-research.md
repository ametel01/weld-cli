# Weld Telegram Bot - Implementation Research Document

This document is grounded in the actual codebase at `src/weld/telegram/` and compares implementation status against the specifications in `telegram-spec.md` and `telegram-spec_spec.md`.

## System Overview

The Telegram bot provides remote weld CLI interaction via long-polling. Users execute weld commands, navigate projects, and monitor task execution from Telegram clients.

**Boundaries:**
- In scope: Project switching, welded subcommands (/doctor, /plan, /interview, /implement, /commit), file fetch/push, run status tracking, allowlisted multi-user chats with per-chat queues
- Out of scope: Webhook mode, general file navigation/editing commands (/ls, /cat, etc.), direct git operations outside weld

**Entry points:**
- `src/weld/telegram/cli.py:707` - `serve()` command starts bot
- `src/weld/telegram/bot.py:124` - `create_bot()` creates aiogram instance

---

## Core Components

| Component | Location | Responsibility | Status |
|-----------|----------|----------------|--------|
| CLI | `cli.py` | Typer commands: init, serve, whoami, doctor, user, projects | ✅ Implemented |
| Bot | `bot.py` | aiogram handlers and command implementations | ✅ Partial |
| Config | `config.py` | TelegramConfig, TelegramAuth, TelegramProject (Pydantic) | ✅ Implemented |
| Auth | `auth.py` | User allowlist validation | ✅ Implemented |
| State | `state.py` | SQLite async state store | ✅ Implemented |
| Queue | `queue.py` | Per-chat FIFO queue | ✅ Implemented |
| Runner | `runner.py` | Async subprocess runner | ✅ Implemented |
| Format | `format.py` | MessageEditor for rate-limited updates | ✅ Implemented |
| Files | `files.py` | Path validation for /fetch and /push | ✅ Implemented |
| Errors | `errors.py` | TelegramError hierarchy | ✅ Partial |

---

## Data Model

### TelegramConfig
```
Location: src/weld/telegram/config.py:56-84
Fields:
  - bot_token: str | None
  - projects: list[TelegramProject]
  - auth: TelegramAuth
```

### TelegramAuth
```
Location: src/weld/telegram/config.py:26-53
Fields:
  - allowed_user_ids: list[int]
  - allowed_usernames: list[str]
Methods:
  - is_user_allowed(user_id, username) -> bool
```

### UserContext
```
Location: src/weld/telegram/state.py:64-72
Fields:
  - user_id: int (PRIMARY KEY)
  - current_project: str | None
  - conversation_state: ConversationState ("idle"|"awaiting_project"|"awaiting_command"|"running")
  - last_message_id: int | None
  - updated_at: datetime
```

### Run
```
Location: src/weld/telegram/state.py:84-95
Fields:
  - id: int | None (auto-increment)
  - user_id: int
  - project_name: str
  - command: str
  - status: RunStatus ("pending"|"running"|"completed"|"failed"|"cancelled")
  - started_at: datetime
  - completed_at: datetime | None
  - result: str | None
  - error: str | None
```

---

## Execution Flows

### Flow: Bot Startup (`weld telegram serve`)
1. `cli.py:707` - `serve()` command entry
2. `cli.py:718` - Load config via `load_config()`
3. `cli.py:729` - Validate config exists and has token
4. `cli.py:749` - Call `asyncio.run(_run_bot(config))`
5. `cli.py:787-788` - Initialize `StateStore`, call `state_store.init()`
6. `cli.py:790` - Create `QueueManager[int]()`
7. `cli.py:793-813` - Register auth middleware (checks allowlist)
8. `cli.py:816-909` - Register command handlers (/start, /help, /use, etc.)
9. `cli.py:912-952` - Start queue consumer background task
10. `cli.py:954-959` - Start cleanup task (hourly)
11. `cli.py:966-968` - Start aiogram polling via `dp.start_polling(bot)`

**[MISSING]** Spec says startup should:
- Sync projects from config to state.db (`cli.py` does NOT do this)
- Mark orphaned "running" runs as "failed" (`cli.py` does NOT do this)
- Prune runs table to last 100 entries (`cli.py` does NOT do this)

### Flow: Command Execution
1. `bot.py:477-562` - `_enqueue_weld_command()` validates context, creates Run, enqueues
2. `cli.py:912-952` - Queue consumer dequeues run_id
3. `cli.py:928` - Get project path from config
4. `cli.py:947` - Call `run_consumer()`
5. `bot.py:924-1109` - `run_consumer()` executes command via `execute_run()`
6. `runner.py:80-281` - `execute_run()` streams output chunks
7. `bot.py:1041-1048` - MessageEditor updates status message with output
8. `bot.py:1051-1066` - Mark run completed/failed, persist final status

**Failure paths:**
- If project not found: Mark run as failed (`cli.py:934-939`)
- If run_consumer raises: Exception logged (`cli.py:949`)
- If command timeout: TelegramRunError raised (`runner.py:165-166`)
- If non-zero exit: TelegramRunError raised (`runner.py:237`)

### Flow: Interactive Prompt Handling
1. `runner.py:177-197` - Output scanned for prompt pattern
2. `runner.py:181` - Yield `("prompt", output_buffer)`
3. `bot.py:1006-1022` - Detect prompt, create inline keyboard
4. `bot.py:44-67` - `create_prompt_keyboard()` builds buttons
5. `bot.py:70-107` - `handle_prompt_callback()` processes button click
6. `runner.py:56-77` - `send_input()` writes response to process stdin

**[PARTIAL]** Prompt detection only handles `Select [N/N/N]:` pattern.
Spec requires additional patterns:
- `(y/n)`, `[Y/n]`, `[y/N]`
- `Continue?`, `Proceed?`, `Apply?`
- Arrow menu: `> [x] Item`

---

## Implemented Bot Commands

| Command | Handler | Location | Status |
|---------|---------|----------|--------|
| `/start` | `start_handler` | `cli.py:816-832` | ✅ Implemented |
| `/help` | `help_handler` | `cli.py:834-854` | ✅ Implemented |
| `/use [project]` | `use_command` | `bot.py:178-270` | ✅ Implemented |
| `/status` | `status_command` | `bot.py:273-356` | ✅ Implemented |
| `/cancel` | `cancel_command` | `bot.py:359-435` | ✅ Implemented |
| `/doctor` | `doctor_command` | `bot.py:564-583` | ✅ Implemented |
| `/plan` | `plan_command` | `bot.py:586-606` | ✅ Implemented |
| `/interview` | `interview_command` | `bot.py:609-629` | ✅ Implemented |
| `/implement` | `implement_command` | `bot.py:632-653` | ✅ Implemented |
| `/commit` | `commit_command` | `bot.py:656-677` | ✅ Implemented |
| `/fetch <path>` | `fetch_command` | `bot.py:680-763` | ✅ Implemented |
| `/push <path>` | `push_command` | `bot.py:803-917` | ✅ Implemented |

### Missing Bot Commands (per spec)

| Command | Spec Description | Status |
|---------|------------------|--------|
| `/weld <cmd>` | Universal weld command execution | ❌ NOT Implemented |
| `/ls [path]` | List directory contents | ❌ NOT Implemented |
| `/tree [path] [depth]` | Show directory tree | ❌ NOT Implemented |
| `/cat <path>` | View file contents (paginated) | ❌ NOT Implemented |
| `/head <path> [lines]` | View first N lines | ❌ NOT Implemented |
| `/find <pattern>` | Find files matching glob | ❌ NOT Implemented |
| `/grep <pattern> [path]` | Search file contents | ❌ NOT Implemented |
| `/file <path>` | Inline file creation | ❌ NOT Implemented |
| `/logs <run_id>` | Full output log of a run | ❌ NOT Implemented |
| `/tail <run_id>` | Stream live output | ❌ NOT Implemented |
| `/runs [n]` | List last N runs | ❌ NOT Implemented |
| `/status <run_id>` | Detailed status of specific run | ❌ NOT Implemented |

**Notes:**
- `/push` must be used as a reply to a document message; otherwise it returns usage instructions.
- `/fetch` falls back to GitHub Gist only for text files; large binary files are rejected.

---

## Invariants

| Invariant | Enforced at | Status |
|-----------|-------------|--------|
| Config file permissions 0o600 | `config.py:176` | ✅ Enforced |
| User must be in allowlist | `cli.py:800-811` (middleware) | ✅ Enforced |
| Path must be within project | `files.py:76-90` | ✅ Enforced |
| No shell=True in subprocess | `runner.py:126-132` | ✅ Enforced |
| Queue max 100 items | `queue.py:61` | ✅ Enforced |
| 2s minimum edit interval | `format.py:148` | ✅ Enforced |
| 600s default command timeout | `runner.py:15` | ✅ Enforced |
| Graceful shutdown: SIGTERM → 5s → SIGKILL | `runner.py:318-327` | ✅ Enforced |
| Result truncated to 3000 bytes | `bot.py:921` | ✅ Enforced |

---

## Spec vs Reality - Divergences

### Configuration & Startup

| Spec Says | Code Does | Classification |
|-----------|-----------|----------------|
| Sync projects from config to state.db on startup | Does NOT sync | Missing |
| Mark orphaned "running" runs as "failed" on startup | Does NOT mark | Missing |
| Prune runs table to last 100 entries | Does NOT prune | Missing |
| Exit with "Run 'weld telegram init' first" on missing config | Exits with similar message (`cli.py:724-726`) | Match |

### Commands

| Spec Says | Code Does | Classification |
|-----------|-----------|----------------|
| `/weld <command>` for universal weld execution | Only specific commands (/plan, /doctor, etc.) | Missing |
| Project navigation: /ls, /tree, /cat, /head | NOT implemented | Missing |
| Search: /find, /grep | NOT implemented | Missing |
| File creation: /file | NOT implemented | Missing |
| Task monitoring: /logs, /tail, /runs, /status <id> | /status exists but no run_id variant | Partial |

### Interactive Prompts

| Spec Says | Code Does | Classification |
|-----------|-----------|----------------|
| Detect `Select [N/N/N]:` | Detects via `PROMPT_PATTERN` (`runner.py:28`) | Match |
| Detect `(y/n)`, `[Y/n]` | NOT detected | Missing |
| Detect `Continue?`, `Proceed?`, `Apply?` | NOT detected | Missing |
| Detect arrow menu `> [x] Item` | NOT detected | Missing |
| 5-minute prompt timeout → cancel run | Uses remaining command timeout (`runner.py:186-195`) | Drift |

### File Handling

| Spec Says | Code Does | Classification |
|-----------|-----------|----------------|
| Upload files to `.weld/telegram/uploads/` | NOT implemented | Missing |
| Reply-to-document injection for `/weld` commands | NOT implemented | Missing |
| Filename conflict handling (spec.1.md, spec.2.md) | NOT implemented | Missing |
| /file content > 4KB check | NOT implemented (no /file command) | Missing |
| /cat pagination with "Next page" button | NOT implemented (no /cat command) | Missing |
| Pagination state: 5-minute TTL | NOT implemented | Missing |

### Output File Detection

| Spec Says | Code Does | Classification |
|-----------|-----------|----------------|
| Scan output for "saved to", "created", etc. | NOT implemented | Missing |
| Add "Download" button if file created | NOT implemented | Missing |

### Search

| Spec Says | Code Does | Classification |
|-----------|-----------|----------------|
| /find uses glob, /grep uses regex | NOT implemented | Missing |
| Results limited to 50 matches | NOT implemented | Missing |
| Respect .gitignore patterns | NOT implemented | Missing |

### Error Handling

| Spec Says | Code Does | Classification |
|-----------|-----------|----------------|
| Rate limit: exponential backoff 1s, 2s, 4s (max 3) | Backoff is 1s, 2s, 4s (`format.py:313`) | Match |
| Message deleted → send new message | Handled (`format.py:322-334`) | Match |
| Queue full → "Queue full. Use /cancel" | Enqueue waits up to 10s; on timeout the bot responds "Failed to queue command. Please try again." | Drift |

### Error Hierarchy

| Spec Says | Code Does | Classification |
|-----------|-----------|----------------|
| `FilePathError` with subclasses | Defined in `files.py:8-21` | Match |
| `TelegramError` hierarchy | Defined in `errors.py:4-17` | Partial |
| `FilePathError` should be under `TelegramError` | `FilePathError` is standalone | Drift |

---

## Technical Debt & Open Questions

### [UNCLEAR] Queue Consumer Architecture
The queue consumer in `cli.py:912-952` polls all active chats in a loop with 1-second delay. This doesn't scale well with many concurrent users, but spec says single-user only.

### [UNCLEAR] State Database Sync
Config is source of truth per spec, but there's no mechanism to sync config projects to state.db on startup. The `projects` table in state.db exists but is never populated from config.

### [MISSING] Crash Recovery
Spec requires marking orphaned "running" runs as "failed" on restart. This is not implemented.

### [MISSING] Run Retention
Spec requires keeping last 100 runs and auto-pruning. Not implemented.

### [INFERRED] Unicode Dash Normalization
`bot.py:457-466` converts Unicode dashes (em-dash, en-dash) to regular hyphens. This handles Telegram's auto-conversion of `--` to em-dash, making flags like `--dry-run` work.

### [DEAD CODE] `TelegramFileError`
`errors.py:12-13` defines `TelegramFileError` but it is never raised anywhere in the codebase. File errors use `FilePathError` hierarchy instead.

---

## Implementation Completeness Summary

### Fully Implemented ✅
- CLI commands: init, serve, whoami, doctor, user management, project management
- Configuration: Load/save TOML, 0o600 permissions, token validation
- Authentication: Allowlist-only, silent rejection, middleware enforcement
- State management: SQLite with async access, contexts/projects/runs tables
- Queue: Per-chat FIFO, 100-item limit, cancellation, cleanup
- Runner: Async subprocess, streaming output, SIGTERM/SIGKILL shutdown
- Message formatting: Rate limiting, chunking, status formatting
- Path validation: Traversal protection, project boundary enforcement
- Basic commands: /start, /help, /use, /status, /cancel
- Weld commands: /doctor, /plan, /interview, /implement, /commit
- File transfer: /fetch (Gist fallback for large text) and /push

### Partially Implemented ⚠️
- Interactive prompts: Only `Select [N/N/N]:` pattern detected
- /status: No run_id variant for detailed status
- Error hierarchy: FilePathError not integrated with TelegramError

### Not Implemented ❌
- Universal `/weld <command>` execution
- Project navigation: /ls, /tree, /cat, /head
- Search: /find, /grep
- File attachment workflow: uploads, reply-to-document injection, /file
- Task monitoring: /logs, /tail, /runs
- Output file detection with "Download" button
- Startup housekeeping: orphan cleanup, run pruning, config-to-state sync
- Pagination state with TTL

---

## Recommended Implementation Order

1. **Startup Housekeeping** - Mark orphaned runs, prune runs table
2. **Universal /weld Command** - Single entry point for all weld subcommands
3. **Extended Prompt Detection** - Add y/n, Continue?, arrow menu patterns
4. **File Attachment Workflow** - Upload storage, reply-to-document injection
5. **Project Navigation** - /ls, /tree, /cat, /head
6. **Search Commands** - /find, /grep with gitignore support
7. **Task Monitoring** - /logs, /tail, /runs, /status <id>
8. **Output File Detection** - Scan for created files, add Download button

---

## Appendix: Key Constants

| Constant | Value | Location |
|----------|-------|----------|
| Config path | `~/.config/weld/telegram.toml` | `config.py:92-93` |
| State DB path | `~/.weld/telegram/state.db` | `state.py:98-104` |
| Max queue size | 100 | `queue.py:61` |
| Default dequeue timeout | 300s | `queue.py:12` |
| Command timeout | 600s | `runner.py:15` |
| Graceful shutdown timeout | 5s | `runner.py:18` |
| Message size limit | 4096 bytes | `format.py:13` |
| Min edit interval | 2s | `format.py:148` |
| Max output buffer | 3000 bytes | `bot.py:921` |
| Telegram max download | 50MB | `bot.py:39` |
| Max retry attempts | 3 | `format.py:151` |
| Inactive queue threshold | 3600s (1 hour) | `queue.py:15` |
