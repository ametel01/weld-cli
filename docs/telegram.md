# Telegram Bot

Remote weld interaction via Telegram. Run weld commands on registered projects from anywhere using a Telegram bot.

## Overview

The Telegram bot provides remote access to weld functionality:

- Execute weld commands on your projects remotely
- Real-time streaming output updates
- File transfers (upload/download) with path validation
- Queue system for command ordering
- Allowlist-based user authentication

## Prerequisites

| Tool | Required | Description |
|------|----------|-------------|
| **Telegram account** | Yes | For bot interaction |
| **Bot token** | Yes | Create via [@BotFather](https://t.me/botfather) |
| **weld** | Yes | Base weld installation |
| **aiogram** | Yes | Installed with `weld[telegram]` extra |

## Installation

Install weld with Telegram support:

```bash
# Using uv
uv tool install 'weld-cli[telegram]'

# Or using pip
pip install 'weld-cli[telegram]'

# Verify telegram commands are available
weld telegram --help
```

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
# Add by username
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

### weld telegram serve

Start the bot server.

```bash
weld telegram serve
```

Runs until interrupted with `Ctrl+C`. Requires valid token and at least one allowed user.

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
- Bot token is valid (validates with Telegram API)
- At least one allowed user configured
- At least one project registered
- All project paths exist

### weld telegram user

Manage allowed users.

```bash
# Add a user by username
weld telegram user add <username>

# Add a user by ID
weld telegram user add <user_id>

# Remove a user
weld telegram user remove <id_or_username>

# List allowed users
weld telegram user list
```

Note: Usernames are stored without the `@` prefix (it's stripped automatically).

### weld telegram projects

Manage registered projects.

```bash
# Add a project
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

### Weld Commands

| Command | Description |
|---------|-------------|
| `/doctor` | Run environment check on current project |
| `/plan [spec.md]` | Generate implementation plan |
| `/interview [spec.md]` | Interactive spec refinement |
| `/implement <plan.md>` | Execute plan steps |
| `/commit [-m msg]` | Commit changes with transcripts |

### File Transfer

| Command | Description |
|---------|-------------|
| `/fetch <path>` | Download file from project |
| `/push <path>` | Upload file (reply to a document message) |

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
- **Traversal protection**: Symlinks are resolved before path validation

### Command Safety

- **No shell**: All subprocess calls use explicit argument lists (never `shell=True`)
- **Argument sanitization**: User input is sanitized to prevent injection
- **Timeout enforcement**: All commands have execution timeouts

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

Long-running commands may hit the default timeout. Consider:

- Breaking work into smaller steps
- Using `/status` to monitor progress
- Using `/cancel` if a command is stuck

## See Also

- [Installation](installation.md) - Install weld
- [Commands](commands/index.md) - Full command reference
- [Configuration](configuration.md) - Project configuration
