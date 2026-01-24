# Weld Telegram Bot - Specification

This document describes the Telegram bot integration for weld-cli.

## Overview

The Telegram bot provides remote weld interaction via long-polling. Users can execute weld commands, navigate project files, and monitor task execution from any Telegram client.

## Core Capabilities

1. **Project Navigation** - Browse directories, view files, search content
2. **Universal Commands** - Run any weld command, not a fixed subset
3. **File Attachment** - Easily attach markdown files to weld commands
4. **Task Monitoring** - Track running tasks, view progress, manage execution

## Architecture

```
src/weld/telegram/
├── cli.py        # Typer commands: init, serve, whoami, doctor, user, projects
├── bot.py        # Aiogram handlers and command implementations
├── config.py     # TelegramConfig, TelegramAuth, TelegramProject (Pydantic)
├── auth.py       # User allowlist validation
├── state.py      # SQLite async state store (contexts, projects, runs)
├── queue.py      # Per-chat async FIFO queue for sequential execution
├── runner.py     # Async subprocess runner with streaming output
├── format.py     # MessageEditor for rate-limited Telegram updates
├── files.py      # Path validation for /fetch and /push commands
└── errors.py     # TelegramError exception hierarchy
```

## Configuration

### Config File Location

`~/.config/weld/telegram.toml`

### Config Structure

```toml
bot_token = "123456:ABC..."

[auth]
allowed_user_ids = [123456789]
allowed_usernames = ["myusername"]

[[projects]]
name = "myproject"
path = "/home/user/projects/myproject"
description = "Optional project description"
```

### Security

- Config file permissions set to `0o600` (owner read/write only)
- Bot token stored in plaintext (protected by file permissions)

## State Management

### Database Location

`~/.weld/telegram/state.db` (SQLite, async via aiosqlite)

### Schema

**contexts** - Per-user conversation state:
| Column | Type | Description |
|--------|------|-------------|
| user_id | INTEGER PRIMARY KEY | Telegram user ID |
| current_project | TEXT | Selected project name |
| conversation_state | TEXT | idle/awaiting_project/awaiting_command/running |
| last_message_id | INTEGER | For message editing |
| updated_at | TEXT | ISO timestamp |

**projects** - Project registry (mirrors config):
| Column | Type | Description |
|--------|------|-------------|
| name | TEXT PRIMARY KEY | Project identifier |
| path | TEXT | Filesystem path |
| description | TEXT | Optional description |
| last_accessed_at | TEXT | Updated by /use |
| created_at | TEXT | Registration time |

**runs** - Command execution history:
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment |
| user_id | INTEGER | Telegram user ID |
| project_name | TEXT | Project context |
| command | TEXT | Full command string |
| status | TEXT | pending/running/completed/failed/cancelled |
| started_at | TEXT | Execution start |
| completed_at | TEXT | Execution end |
| result | TEXT | Output (truncated to 3000 bytes) |
| error | TEXT | Failure reason |

## CLI Commands

### Setup

```bash
weld telegram init [--token TOKEN] [--force]   # Configure bot token
weld telegram serve                             # Start long-polling server
weld telegram whoami                            # Show bot identity
weld telegram doctor                            # Validate environment
```

### User Management

```bash
weld telegram user add <id_or_username>    # Add to allowlist
weld telegram user remove <id_or_username> # Remove from allowlist
weld telegram user list                    # Show allowed users
```

### Project Management

```bash
weld telegram projects add <name> <path> [--description DESC]
weld telegram projects remove <name>
weld telegram projects list
```

## Bot Commands

### Project Context

| Command | Description |
|---------|-------------|
| `/use [project]` | Switch project context or show current |
| `/status` | Show queue and run status |
| `/cancel [run_id]` | Cancel active run or all pending |

### Project Navigation

| Command | Description |
|---------|-------------|
| `/ls [path]` | List directory contents (default: project root) |
| `/tree [path] [depth]` | Show directory tree (default depth: 2) |
| `/cat <path>` | View file contents (paginated for large files) |
| `/head <path> [lines]` | View first N lines (default: 20) |
| `/find <pattern>` | Find files matching glob pattern |
| `/grep <pattern> [path]` | Search file contents |

### Universal Weld Commands

Any weld command can be executed by prefixing with `/weld`:

```
/weld <command> [args...]
```

Examples:
- `/weld doctor` - Run environment check
- `/weld plan spec.md` - Generate plan from spec
- `/weld implement plan.md --phase 1` - Execute phase 1
- `/weld research "how does auth work"` - Research query
- `/weld commit -m "Add feature"` - Commit changes

The bot passes arguments directly to the weld CLI. All weld subcommands are supported.

### File Attachment Workflow

Files can be attached to weld commands in two ways:

**Method 1: Upload then reference**
1. Send a markdown file as a document
2. Bot saves to `.weld/telegram/uploads/<filename>`
3. Use the path in subsequent commands: `/weld plan .weld/telegram/uploads/spec.md`

**Method 2: Inline file creation**
```
/file spec.md
---
# My Specification
Feature requirements here...
---
```
Creates `spec.md` in project root, ready for use in commands.

**Method 3: Reply with command**
1. Send a markdown file as a document
2. Reply to the document with a command: `/weld plan`
3. Bot automatically uses the uploaded file as the argument

### Task Monitoring

| Command | Description |
|---------|-------------|
| `/status` | Overview of all tasks (pending, running, recent) |
| `/status <run_id>` | Detailed status of specific run |
| `/logs <run_id>` | Full output log of a run |
| `/tail <run_id>` | Stream live output (auto-updates) |
| `/runs [n]` | List last N runs (default: 10) |

### File Transfer

| Command | Description |
|---------|-------------|
| `/fetch <path>` | Download file from project |
| `/push <path>` | Upload file (reply to document) |

### Help

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | List available commands |
| `/help <command>` | Detailed help for specific command |

## Queue System

### Design

- Per-chat FIFO ordering
- Sequential execution within each chat
- Concurrent processing across different chats
- Maximum 100 items per chat queue
- Default dequeue timeout: 300 seconds

### Cancellation

- `/cancel` marks all pending items as cancelled
- Cancelled items are skipped during dequeue
- Active runs receive SIGTERM, then SIGKILL after 5s

## Command Execution

### Runner Behavior

1. Uses `asyncio.create_subprocess_exec()` (never `shell=True`)
2. Concurrent stdout/stderr reading with 0.1s intervals
3. Output accumulated in buffer (max 3000 bytes for display)
4. Default timeout: 600 seconds (10 minutes)
5. Graceful shutdown: SIGTERM → wait 5s → SIGKILL

### Interactive Prompt Handling

When weld commands prompt for input (e.g., `Select [1/2/3]:`):
1. Bot detects prompt pattern in output
2. Sends inline keyboard with options
3. User clicks option button
4. Response written to stdin
5. Execution continues

### Streaming Output

- Real-time status updates as commands run
- MessageEditor enforces 2-second minimum between edits
- Exponential backoff on Telegram rate limits (429 errors)
- Output chunked to fit 4096-byte Telegram limit

## Project Navigation

### Directory Listing (`/ls`, `/tree`)

1. Path defaults to project root if omitted
2. Output formatted as monospace code block
3. `/ls` shows: type indicator, size, modified date, name
4. `/tree` respects `.gitignore` patterns
5. Hidden files (dotfiles) excluded by default, use `--all` to include

### File Viewing (`/cat`, `/head`)

1. Files > 4000 chars: Paginated with "Next page" button
2. Binary files: Show file info instead of contents
3. Syntax highlighting via markdown code blocks (auto-detect language)
4. Line numbers included for reference

### Search (`/find`, `/grep`)

1. `/find` uses glob patterns (e.g., `*.md`, `src/**/*.py`)
2. `/grep` uses regex, searches file contents
3. Results limited to 50 matches, with "Show more" option
4. Results show relative paths from project root

## File Attachment

### Upload Storage

Uploaded files saved to: `<project>/.weld/telegram/uploads/`

Structure:
```
.weld/telegram/uploads/
├── spec.md              # Most recent upload with this name
├── spec.1.md            # Previous version (auto-numbered)
└── plan-2024-01-23.md   # Timestamped if conflicts
```

### Document Message Handling

When user sends a document (file attachment):
1. Validate file type (allow: `.md`, `.txt`, `.toml`, `.yaml`, `.json`)
2. Download to uploads directory
3. Reply with confirmation: "Saved to `.weld/telegram/uploads/spec.md`"
4. If user replies to this message with a command, auto-inject path

### Reply-to-Document Commands

When a `/weld` command is a reply to a document message:
1. Download the document if not already saved
2. Detect which argument expects a file path
3. Inject the uploaded path as that argument

Example:
```
User: [sends spec.md as document]
Bot: "Saved to .weld/telegram/uploads/spec.md"
User: [replies] /weld plan
Bot: [executes] weld plan .weld/telegram/uploads/spec.md
```

### Inline File Creation (`/file`)

Syntax:
```
/file <path>
<content>
```

Rules:
1. Path relative to project root
2. Creates parent directories if needed
3. Overwrites existing file (with warning if exists)
4. Content is everything after the first newline

## File Transfer

### /fetch

1. Validates path is within registered project
2. Checks file exists and is readable
3. Files ≤ 50MB: Send via Telegram
4. Files > 50MB (text only): Upload to GitHub Gist, return URL

### /push

1. Must be reply to a document message
2. Validates destination within project
3. Downloads from Telegram (≤ 50MB limit)
4. Creates parent directories if needed
5. Writes file to filesystem

## Authentication

### Allowlist Model

- Bot ignores messages from unauthorized users
- No response sent to unauthorized attempts (silent rejection)
- Attempts logged as warnings

### Validation

Users must match at least one:
- `auth.allowed_user_ids` (numeric Telegram user ID)
- `auth.allowed_usernames` (Telegram username)

### Command Argument Sanitization

Removes shell metacharacters from command arguments:
- Blocked: `;`, `&`, `|`, `$`, backticks, `()`, `{}`, `<>`, newlines, null bytes
- Allowed: alphanumeric, space, dash, underscore, dot, forward slash, quotes

## Path Traversal Protection

### Validation Rules

1. Path must resolve within a registered project directory
2. Symlink attacks detected by comparing resolved path to project root
3. `/fetch` requires file to exist
4. `/push` allows non-existent files (for creation)

### Errors

- `PathTraversalError`: Path escapes project boundary
- `PathNotAllowedError`: Path not within any registered project
- `PathNotFoundError`: File doesn't exist (fetch only)

## Error Handling

### Exception Hierarchy

```
TelegramError (base)
├── TelegramAuthError     # User not authorized
├── TelegramFileError     # File operations
├── TelegramRunError      # Command execution
└── FilePathError         # Path validation
    ├── PathTraversalError
    ├── PathNotAllowedError
    └── PathNotFoundError
```

### Recovery Patterns

| Error Type | Behavior |
|------------|----------|
| Rate limit (429) | Exponential backoff, retry up to 3 times |
| Message deleted | Send new message, continue |
| Run failed | Mark as failed in state, notify user |
| Auth failure | Log warning, no response to user |

## Message Formatting

### Status Message Format

```
📝 *Run #123*
Project: `myproject`
Command: `weld plan spec.md`
Status: running ▶️
Started: 2024-01-23 14:30:45

Output:
```
[last 500 chars of output]
```
```

### Status Emoji

| Status | Emoji |
|--------|-------|
| pending | ⏳ |
| running | ▶️ |
| completed | ✅ |
| failed | ❌ |
| cancelled | ⏹️ |

## Constraints

| Constraint | Value | Mitigation |
|------------|-------|------------|
| Message size | 4096 bytes | Chunking |
| Edit rate limit | Telegram-enforced | 2s minimum interval |
| File download | 50 MB | Gist fallback for text |
| Command timeout | 600 seconds | Configurable |
| Queue size | 100 per chat | Prevents memory exhaustion |

## Dependencies

- **aiogram**: Telegram Bot API framework (async)
- **aiosqlite**: Async SQLite access
- **gh CLI**: GitHub Gist uploads for large files

## Task Monitoring

### Status Overview (`/status`)

Shows dashboard of current state:
```
📊 *Project: myproject*

▶️ *Running (1)*
  #42: weld implement plan.md (2m 34s)

⏳ *Pending (2)*
  #43: weld commit -m "Add auth"
  #44: weld doctor

✅ *Recent (last 3)*
  #41: weld plan spec.md - completed (1m 12s)
  #40: weld research auth - completed (45s)
  #39: weld doctor - completed (3s)
```

### Run Details (`/status <run_id>`)

Shows detailed info for specific run:
```
📝 *Run #42*
Project: `myproject`
Command: `weld implement plan.md`
Status: running ▶️
Started: 2024-01-23 14:30:45
Duration: 2m 34s

Progress: Phase 2/3, Step 4/6
Files modified: 3
  - src/auth.py
  - src/config.py
  - tests/test_auth.py

[View Logs] [Cancel]
```

### Live Tail (`/tail <run_id>`)

Streams output in real-time:
1. Sends initial message with last 20 lines
2. Edits message every 2 seconds with new output
3. Auto-stops when run completes
4. User can send `/tail stop` to stop following

### Run History (`/runs`)

Lists recent runs with filters:
```
/runs              # Last 10 runs
/runs 20           # Last 20 runs
/runs --failed     # Only failed runs
/runs --today      # Today's runs only
```

## Example Flows

### File Navigation Flow

```
User: /use myproject
Bot: "Switched to myproject (/home/user/projects/myproject)"

User: /tree src 3
Bot:
  src/
  ├── weld/
  │   ├── cli.py
  │   ├── commands/
  │   │   ├── init.py
  │   │   └── plan.py
  │   └── core/
  │       └── ...
  └── tests/

User: /cat src/weld/cli.py
Bot: [displays file with syntax highlighting]

User: /grep "def plan" src/
Bot:
  src/weld/commands/plan.py:15: def plan(spec_file: Path):
  src/weld/core/plan_parser.py:42: def plan_from_markdown(content: str):
```

### File Attachment Flow

```
User: [uploads spec.md as document]
Bot: "📎 Saved to .weld/telegram/uploads/spec.md"

User: [replies to above] /weld plan
Bot: "⏳ Queued: weld plan .weld/telegram/uploads/spec.md (#45)"
Bot: [streams output as plan generates]
Bot: "✅ Run #45 completed. Output saved to .weld/plan/spec_plan.md"

User: /fetch .weld/plan/spec_plan.md
Bot: [sends file as document]
```

### Task Monitoring Flow

```
User: /weld implement plan.md
Bot: "⏳ Queued as #46"
Bot: "▶️ Running #46: weld implement plan.md"

User: /status 46
Bot: [shows detailed status with progress]

User: /tail 46
Bot: [starts streaming live output]

[command completes]
Bot: "✅ Run #46 completed in 3m 42s"
```

### Universal Command Flow

```
User: /weld research "how does the auth middleware work"
Bot: "⏳ Queued as #47"
Bot: [streams research output]
Bot: "✅ Completed. See .weld/research/auth_middleware.md"

User: /weld discover --scope auth
Bot: "⏳ Queued as #48"
Bot: [streams discovery output]
```

## Version History

| Version | Changes |
|---------|---------|
| v2 | Added: project navigation, universal weld commands, file attachment workflow, task monitoring |
| v1 | Initial specification document |
