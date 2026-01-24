# Telegram Bot

Remote weld interaction via Telegram. Run weld commands on registered projects from anywhere using a Telegram bot.

## Overview

The Telegram bot provides remote access to weld functionality:

- Execute weld commands on your projects remotely (including `/weld <subcommand>`)
- Rate-limited status updates with output tails
- File transfers (upload/download) with path validation and optional auto-upload handling
- Per-chat queue system for command ordering
- Allowlist-based user authentication (supports multiple users)

## Prerequisites

| Tool | Required | Description |
|------|----------|-------------|
| **Telegram account** | Yes | For bot interaction |
| **Bot token** | Yes | Create via [@BotFather](https://t.me/botfather) |
| **GitHub CLI (`gh`)** | Optional | Required only for `/fetch` fallback to GitHub Gist |
| **Git** | Optional | Required for `/tree`, `/find`, and `/grep` (respects `.gitignore`) |

## Quick Start

### 1. Create a Bot

1. Open Telegram and message [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token (looks like `123456789:ABCdef...`)

### 2. Initialize Configuration

```bash
# Interactive setup
weld telegram init

# Or provide token directly
weld telegram init --token "YOUR_BOT_TOKEN"
```

This creates `~/.config/weld/telegram.toml` with restricted permissions (0600).

### 3. Add Allowed Users

```bash
# Add by username (@ prefix is stripped automatically)
weld telegram user add yourusername

# Or add by user ID
weld telegram user add 123456789

# List allowed users
weld telegram user list
```

!!! tip "Finding Your User ID"
    Message [@userinfobot](https://t.me/userinfobot) on Telegram to get your user ID.

### 4. Register Projects

```bash
# Add a project
weld telegram projects add myproject /home/user/projects/myproject

# Add with description
weld telegram projects add myproject /path/to/project -d "My awesome project"

# List registered projects
weld telegram projects list
```

### 5. Start the Bot

```bash
weld telegram serve
```

The bot runs in long-polling mode. Press `Ctrl+C` to stop.

## CLI Commands

### weld telegram init

Initialize Telegram bot configuration.

```bash
weld telegram init [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--token` | `-t` | Bot token (prompts if not provided) |
| `--force` | `-f` | Overwrite existing configuration |

The init command validates the token with the Telegram API before saving. If weld is not available globally in PATH, it offers to install weld globally using `uv tool install`.

### weld telegram serve

Start the bot server.

```bash
weld telegram serve
```

Runs until interrupted with `Ctrl+C`. Requires valid bot token. If no allowed users are configured, displays a warning but still starts (the bot will reject all messages).

### weld telegram whoami

Show bot identity and authentication status.

```bash
weld telegram whoami
```

Output:
```
Status: Authenticated
Bot: @your_bot_name
Config: /home/user/.config/weld/telegram.toml
Allowed users: 2 IDs, 1 usernames
Projects: 3 registered
```

### weld telegram doctor

Validate Telegram bot setup.

```bash
weld telegram doctor
```

Checks:

- aiogram dependency installed
- Configuration file exists and is valid
- Bot token is set and valid (validates with Telegram API)
- At least one allowed user configured (warning if none)
- At least one project registered (warning if none)
- All project paths exist and are directories

### weld telegram user

Manage allowed users.

```bash
# Add a user by username (@ prefix stripped automatically)
weld telegram user add <username>

# Add a user by ID (numeric values treated as IDs)
weld telegram user add <user_id>

# Remove a user
weld telegram user remove <id_or_username>

# List allowed users
weld telegram user list
```

Note: Usernames are stored without the `@` prefix (it's stripped automatically if provided).

### weld telegram projects

Manage registered projects.

```bash
# Add a project (path must exist and be a directory)
weld telegram projects add <name> <path> [-d "description"]

# Remove a project
weld telegram projects remove <name>

# List all projects
weld telegram projects list
```

## Bot Commands

Once the bot is running, use these commands in Telegram:

### Project Management

| Command | Description |
|---------|-------------|
| `/start` | Show welcome message and command list |
| `/help` | Detailed help for all commands |
| `/use` | Show current project and available projects |
| `/use <project>` | Switch to specified project |

### Run Management

| Command | Description |
|---------|-------------|
| `/status` | Show current run, queue status, and recent history |
| `/cancel` | Cancel active run and clear pending queue |
| `/runs [--failed] [--today] [n]` | List recent runs (default 10, max 50) |
| `/logs <run_id> [page\|all]` | Show paginated logs or download full log |
| `/tail <run_id\|stop>` | Stream live output from a running run |
| `/status <run_id>` | Show detailed status for a specific run |

Details:
- `/status` shows the current project, active run (if any), queue size, pending commands, and the last three terminal runs.
- `/cancel` marks running and pending runs as cancelled and clears the per-chat queue.
- `/runs` supports `--failed`, `--today`, and a numeric limit (capped at 50).
- `/logs <run_id> all` sends the full log as a file when output is large.
- `/tail` allows one active tail per user; use `/tail stop` to stop streaming.
- `/status <run_id>` includes timestamps, duration, and a truncated result or error.

### Weld Commands

| Command | Description |
|---------|-------------|
| `/doctor` | Run environment check on current project |
| `/plan [spec.md]` | Generate implementation plan |
| `/interview [spec.md]` | Interactive spec refinement |
| `/implement <plan.md>` | Execute plan steps |
| `/commit [-m msg]` | Commit changes with transcripts |
| `/weld <subcommand> [args]` | Run any weld subcommand (with safety checks) |

Notes:
- `/weld` blocks unsafe subcommands like `telegram`.
- When replying to a document message, `/weld` (and the dedicated weld commands above) will auto-inject the uploaded file path as the first argument.

### Project Navigation

| Command | Description |
|---------|-------------|
| `/ls [path] [--all]` | List directory contents (default project root) |
| `/tree [path] [depth]` | Show directory tree (depth 1–10, default 3) |
| `/cat <path>` | View file contents with syntax highlighting and pagination |
| `/head <path> [lines]` | View first N lines (default 20) |

Notes:
- `/cat` and `/head` only display text files from the allowlist; binary files must be downloaded via `/fetch`.
- `/tree` respects `.gitignore` by using `git ls-files`; it requires Git and a repo in the project.
- `/cat` pagination state expires after 5 minutes of inactivity.

### Search

| Command | Description |
|---------|-------------|
| `/find <glob>` | Find files by glob pattern (limit 50) |
| `/grep <pattern> [path]` | Regex search in files (limit 50) |

Notes:
- `/find` and `/grep` respect `.gitignore` via `git ls-files` and require Git.
- `/grep` skips binary files and truncates long matched lines.

### File Transfer

| Command | Description |
|---------|-------------|
| `/fetch <path>` | Download file from project |
| `/push <path>` | Upload file (reply to a document message) |
| `/file <path> <content>` | Create/overwrite a file from inline content (max 4KB) |

Notes:
- `/push` must be sent as a reply to a document message.
- `/fetch` uses GitHub Gist as a fallback only for large text files and requires the `gh` CLI with `gh auth login`.
- `/fetch` rejects directories and only allows paths within registered projects (absolute or relative).
- `/push` creates parent directories as needed and overwrites existing files.
- `/file` writes UTF-8 text, creates parent directories, and warns when overwriting.

### File Uploads (Automatic)

If you send a document without replying to `/push`, the bot automatically stores it under:

```
.weld/telegram/uploads/<sanitized-filename>
```

Notes:
- Allowed extensions are a small safe allowlist (e.g., `.md`, `.txt`, `.json`, `.yaml`, `.toml`, `.py`, `.js`, `.ts`, `.sh`).
- Filename conflicts are resolved with numeric suffixes (e.g., `spec.1.md`).
- You can reply to that document with `/weld`, `/plan`, `/interview`, `/implement`, or `/commit` and the bot will auto-inject the uploaded file path.
- Uploads are limited to 50MB (Telegram bot download limit).

## Usage Examples

### Basic Workflow

```
You: /use myproject
Bot: Switched to project: myproject

You: /doctor
Bot: Queued: weld doctor
     Project: myproject
     Position: next up

Bot: [streaming output...]
     ✓ git: installed
     ✓ gh: authenticated
     ...
```

### Generate and Execute a Plan

```
You: /plan specs/auth-feature.md
Bot: Queued: weld plan specs/auth-feature.md
     [streaming output as plan is generated...]

You: /fetch .weld/plan/auth-feature-20260117.md
Bot: [sends plan file]

You: /implement .weld/plan/auth-feature-20260117.md --phase 1
Bot: [streaming output as phase 1 executes...]

You: /commit
Bot: [creates commit with transcript]
```

### File Upload

```
You: [send a file to the chat]

You: [reply to the file with]
     /push src/config.py
Bot: Saved to: /home/user/projects/myproject/src/config.py
```

## Configuration

Configuration file: `~/.config/weld/telegram.toml`

```toml
# Bot token from @BotFather
bot_token = "123456789:ABCdef..."

# User authentication
[auth]
allowed_user_ids = [123456789, 987654321]
allowed_usernames = ["alice", "bob"]

# Registered projects
[[projects]]
name = "myproject"
path = "/home/user/projects/myproject"
description = "Main project"

[[projects]]
name = "backend"
path = "/home/user/projects/backend"
```

### Configuration Options

| Key | Type | Description |
|-----|------|-------------|
| `bot_token` | string | Telegram Bot API token |
| `auth.allowed_user_ids` | list[int] | User IDs allowed to use the bot |
| `auth.allowed_usernames` | list[str] | Usernames allowed (without @) |
| `projects` | list | Registered projects with name, path, description |

## Security Model

### Allowlist Authentication

- **Allowlist-only**: Bot ignores all messages from users not in the allowlist
- **Silent rejection**: Unauthorized access attempts are logged but receive no response
- **Dual validation**: Users can be allowed by ID, username, or both

### File Protection

- **Token protection**: Config file is set to `0600` (owner read/write only)
- **Project isolation**: Commands execute only in registered project directories
- **Path validation**: `/fetch` and `/push` validate paths against registered projects
- **Traversal protection**: Symlinks are resolved before path validation to prevent escaping project boundaries

### Command Safety

- **No shell**: All subprocess calls use explicit argument lists (never `shell=True`)
- **Argument sanitization**: User input is sanitized to remove shell metacharacters (`;`, `&`, `|`, `$`, `` ` ``, etc.)
- **Unicode normalization**: Telegram auto-converts `--` to em-dash; the bot normalizes these back to regular hyphens
- **Timeout enforcement**: Commands have a 10-minute execution timeout with graceful SIGTERM then SIGKILL

## Architecture

```
~/.config/weld/telegram.toml    # Configuration (bot token, users, projects)
~/.weld/telegram/state.db       # SQLite state (contexts, runs, history)
```

### Components

| Module | Purpose |
|--------|---------|
| `cli.py` | CLI commands (init, serve, whoami, doctor, user, projects) |
| `bot.py` | Aiogram handlers and command implementations |
| `config.py` | Pydantic configuration models |
| `auth.py` | User allowlist validation |
| `state.py` | SQLite state persistence |
| `queue.py` | Per-chat FIFO command queue |
| `runner.py` | Async subprocess execution with streaming |
| `format.py` | Message formatting with rate-limited editing |
| `files.py` | File upload/download with path validation |
| `errors.py` | Error hierarchy (TelegramError, TelegramAuthError, TelegramRunError) |

### Message Flow

```
User Message
    ↓
Auth Middleware (check allowlist)
    ↓
Command Handler (parse command)
    ↓
Queue Manager (enqueue run)
    ↓
Queue Consumer (dequeue and execute)
    ↓
Runner (async subprocess with streaming)
    ↓
Message Editor (rate-limited status updates)
```

### Interactive Prompts

Commands that require user input (like `weld commit` session selection) display inline keyboard buttons. The bot currently detects prompts matching the `Select [options]:` pattern and presents options as clickable buttons.

### Large File Handling

For files larger than 50MB, `/fetch` falls back to uploading the file to GitHub Gist (text files only) and returns the gist URL instead of the file directly. This requires the `gh` CLI to be installed and authenticated; binary files are rejected.

## Operational Limits

- Queue size: 100 pending runs per chat
- Command timeout: 10 minutes (SIGTERM then SIGKILL after 5s)
- Status output buffer: last 3000 bytes stored; status preview shows the last 500 characters
- Message edits: rate-limited to one edit every 2 seconds

## Troubleshooting

### Bot not responding

1. Check bot is running: `weld telegram serve`
2. Verify your user ID is in allowlist: check `~/.config/weld/telegram.toml`
3. Run diagnostics: `weld telegram doctor`

### Token invalid

1. Get a new token from [@BotFather](https://t.me/botfather)
2. Re-initialize: `weld telegram init --force`

### Project not found

1. List projects: `weld telegram projects list`
2. Check paths exist: verify directories in config
3. Add missing project: `weld telegram projects add <name> <path>`

### Permission denied on config

The config file should have `0600` permissions:

```bash
chmod 600 ~/.config/weld/telegram.toml
```

### Commands timing out

Long-running commands have a 10-minute timeout. Consider:

- Breaking work into smaller steps
- Using `/status` to monitor progress
- Using `/cancel` if a command is stuck

### Cannot switch projects

You cannot switch projects while a command is running. Wait for the current command to complete or use `/cancel` first.

## See Also

- [Installation](installation.md) - Install weld
- [Commands](commands/index.md) - Full command reference
- [Configuration](configuration.md) - Project configuration
