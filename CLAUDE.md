# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build and Development Commands

```bash
# Setup
make setup                    # Full dev setup (deps + pre-commit hooks)
eval $(make venv-eval)        # Activate virtual environment

# Testing
make test                     # Run all tests
make test-unit                # Unit tests only (@pytest.mark.unit)
make test-cli                 # CLI integration tests (@pytest.mark.cli)
make test-cov                 # Tests with coverage report
.venv/bin/pytest tests/test_config.py -v  # Run single test file
.venv/bin/pytest tests/test_config.py::test_function_name -v  # Run single test

# Code Quality
make check                    # All quality checks (lint + format + types)
make lint-fix                 # Auto-fix linting issues
make format                   # Format code with ruff
make typecheck                # Run pyright

# Security
make security                 # Run pip-audit + detect-secrets

# Full CI
make ci                       # Complete CI pipeline

# Local Installation
make bin-install              # Install weld CLI globally via uv tool
make bin-uninstall            # Remove global installation and clean cache
```

## Architecture

Weld is a human-in-the-loop coding harness that generates structured prompts for AI-assisted development. Core workflow: research → plan → implement → review → commit with full transcript provenance.

### Layered Structure

```
src/weld/
├── cli.py              # Typer entry point, global options (--debug, --json, --dry-run)
├── commands/           # CLI command handlers (thin layer)
│   ├── init.py         # weld init - Initialize .weld/ directory
│   ├── plan.py         # weld plan - Generate implementation plans
│   ├── research.py     # weld research - Research prompts
│   ├── discover.py     # weld discover - Brownfield codebase discovery
│   ├── interview.py    # weld interview - Interactive spec refinement
│   ├── doc_review.py   # weld review - Document/code review
│   ├── implement.py    # weld implement - Interactive plan execution
│   ├── commit.py       # weld commit - Session-based commits with transcripts
│   ├── prompt.py       # weld prompt - Manage prompt customizations
│   └── doctor.py       # weld doctor - Environment validation
├── core/               # Business logic
│   ├── history.py      # JSONL command history tracking
│   ├── weld_dir.py     # .weld directory utilities
│   ├── plan_parser.py  # Phased plan parsing (Phase, Step, Plan)
│   ├── discover_engine.py    # Codebase discovery prompts
│   ├── interview_engine.py   # Specification refinement prompts
│   ├── doc_review_engine.py  # Document review prompts
│   └── prompt_customizer.py  # Prompt prefix/suffix customization
├── services/           # External integrations
│   ├── git.py          # Git operations (never shell=True)
│   ├── claude.py       # Claude CLI integration with streaming
│   ├── session_detector.py    # Auto-detect Claude Code sessions
│   ├── session_tracker.py     # Track file changes per session
│   ├── transcript_renderer.py # Render JSONL to markdown (redaction, truncation)
│   ├── gist_uploader.py       # Upload transcripts via gh CLI
│   └── transcripts.py         # Legacy transcript tool wrapper
├── models/             # Pydantic data models
│   ├── session.py      # SessionActivity, TrackedSession
│   ├── discovery.py    # DiscoverMeta
│   └── validation.py   # Issue, Issues, Severity
├── config.py           # WeldConfig, TaskModelsConfig, TranscriptsConfig
├── output.py           # OutputContext for console/JSON/dry-run handling
└── logging.py          # Logging configuration with debug file support
```

### Key Design Patterns

- **Commands delegate to core**: `commands/*.py` handle CLI parsing, validate inputs, then call `core/*.py` for business logic
- **Services wrap external CLIs**: All subprocess calls go through `services/` (never `shell=True`, always with timeouts)
- **JSONL append-only logs**: Command history (`.weld/<command>/history.jsonl`) and session registry (`.weld/sessions/registry.jsonl`)
- **Automatic session tracking**: `weld implement` automatically captures file changes for transcript provenance
- **Pydantic everywhere**: All data structures use Pydantic models for validation

### Critical Workflows

#### Session-Based Commits
`weld commit` groups staged files by their originating Claude Code session:
1. Detect current session from `~/.claude/projects/`
2. Load session registry from `.weld/sessions/registry.jsonl`
3. Group staged files by session ID
4. For each session: render transcript → upload gist → create commit with gist URL trailer
5. Use `--no-session-split` to create a single commit for all files

#### Transcript Generation (Native)
Transcripts are rendered from Claude JSONL session files without external binaries:
1. **Session detection**: Auto-find active session in `~/.claude/projects/`
2. **Activity tracking**: Record file changes automatically during `weld implement`
3. **Rendering**: Parse JSONL, redact secrets, truncate large blocks, apply size limits
4. **Upload**: Use `gh gist create` to publish (secret/public per config)

#### Implement Command
Interactive plan execution with atomic checkpointing:
1. Parse phased plan with `plan_parser.py`
2. Present arrow-key navigable menu (`simple-term-menu`)
3. Execute selected step, checkpoint progress
4. Graceful Ctrl+C handling preserves completed steps

**Auto-Commit Feature (`--auto-commit`)**:
- Prompts user to commit changes after each step completes
- Automatically stages all changes and creates session-based commits
- Non-blocking: commit failures don't stop the implement flow
- Skips prompt if no changes detected
- Usage: `weld implement plan.md --auto-commit`

**Review Prompt Feature**:
- After each step completes, prompts: "Review changes from step X?"
- If yes, prompts: "Apply fixes directly to files?"
- Runs `weld review --diff [--apply]` accordingly
- Non-blocking: review failures don't stop implement flow
- Always available (independent of --auto-commit flag)
- Saves review artifacts to `.weld/reviews/{timestamp}/`

### Session Tracking

Weld automatically tracks file changes during `weld implement` commands,
enabling session-based commit grouping.

#### How It Works

When you run `weld implement`:
1. Detects current Claude Code session from `~/.claude/projects/`
2. Takes snapshot of repo files before execution
3. Executes plan step/phase
4. Takes snapshot after execution
5. Records created/modified files to `.weld/sessions/registry.jsonl`

#### Commit Grouping

When you run `weld commit`:
1. Groups staged files by originating session
2. Creates one commit per session
3. Uploads transcript from session JSONL to GitHub Gist
4. Adds gist URL as commit trailer

#### No Configuration Needed

Tracking is automatic for implement commands. No flags or setup required.

If Claude session is not detected (running outside Claude Code),
tracking is skipped silently and commit uses logical grouping fallback.

### Prompt Customization

Weld supports customizing prompts for each task type via the `[prompts]` section in `.weld/config.toml`.
Customizations are applied in layers: `global_prefix → task_prefix → prompt → task_suffix → global_suffix`.

#### CLI Commands

```bash
weld prompt                          # List all prompt types with customization status
weld prompt list                     # Same as above (explicit)
weld prompt show <type>              # Show customization for a task type
weld prompt show research --raw      # Output raw template (pipe-friendly)
weld prompt show discover --focus "security"  # Preview with specific focus
weld prompt export <dir> --raw       # Export all templates as markdown files
weld prompt export --format toml     # Export customizations as TOML (stdout)
weld prompt export -o prompts.json --format json  # Export as JSON file
```

#### Task Types

Available task types for customization:
- `discover`: Brownfield codebase discovery and analysis
- `interview`: Interactive specification refinement
- `research`: Research prompts for gathering context
- `research_review`: Review of research outputs
- `plan_generation`: Implementation plan generation
- `plan_review`: Review of generated plans
- `implementation`: Code implementation phase
- `implementation_review`: Review of implemented code
- `fix_generation`: Generate fixes for review feedback

#### Configuration Example

```toml
[prompts]
# Global prefix/suffix applied to ALL prompts
global_prefix = "This is a Python 3.12 project using FastAPI and SQLAlchemy."
global_suffix = "Always include type hints and docstrings."

# Per-task customizations
[prompts.discover]
prefix = "Focus on the data model and API layer."
default_focus = "architecture"

[prompts.research]
prefix = "Consider security implications."
suffix = "Include a risk assessment section."
default_focus = "security"

[prompts.plan_generation]
prefix = "Plans should be incremental and testable."
```

#### How Customizations Apply

When a prompt is generated for a task (e.g., `weld research`):
1. Global prefix is prepended (if configured)
2. Task-specific prefix is prepended (if configured)
3. The base prompt for the task
4. Task-specific suffix is appended (if configured)
5. Global suffix is appended (if configured)

The `default_focus` provides a fallback value for the `--focus` flag when not specified on the command line.

### Configuration System

Config file: `.weld/config.toml` (TOML format, Pydantic validation)

Key sections:
- `[project]`: Project metadata
- `[checks]`: Multi-category checks (lint/test/typecheck with execution order)
- `[codex]` / `[claude]`: Provider defaults (exec path, model, timeout)
- `[task_models]`: Per-task model assignment (discover, plan_generation, implementation, etc.)
- `[prompts]`: Prompt customization (global/per-task prefix, suffix, default_focus)
- `[transcripts]`: Transcript generation (enabled, visibility)
- `[git]`: Commit trailer configuration
- `[loop]`: Implement-review-fix loop settings

Config migration: Old `[claude.transcripts]` auto-migrates to top-level `[transcripts]`

### Version Control

`weld init` automatically adds `.weld/` to `.gitignore`:

```gitignore
.weld/
```

The entire `.weld/` directory is local-only and not tracked in git. This includes config, sessions, reviews, and history.

If `.gitignore` already contains `.weld/`, `weld init` skips updating it.

### Telegram Bot

Remote weld interaction via Telegram. Runs as a long-polling bot for executing weld commands on registered projects.

#### Architecture

```
src/weld/telegram/
├── cli.py              # Typer commands: init, serve, whoami, doctor, projects
├── bot.py              # Aiogram handlers and command implementations
├── config.py           # TelegramConfig, TelegramAuth, TelegramProject (Pydantic)
├── auth.py             # User allowlist validation
├── state.py            # SQLite state store (contexts, projects, runs)
├── queue.py            # Per-chat async queue for sequential command execution
├── runner.py           # Subprocess runner for weld commands
├── format.py           # MessageEditor for streaming Telegram updates
├── files.py            # File upload/download handlers
└── errors.py           # TelegramError hierarchy
```

#### CLI Commands

```bash
# Setup
weld telegram init                          # Configure bot token interactively
weld telegram init --token <TOKEN>          # Configure with token directly

# Diagnostics
weld telegram whoami                        # Show bot identity and auth status
weld telegram doctor                        # Validate setup (deps, config, token, users)

# User management
weld telegram user add <id_or_username>     # Add user to allowlist (by ID or @username)
weld telegram user remove <id_or_username>  # Remove user from allowlist
weld telegram user list                     # List allowed users

# Project management
weld telegram projects add <name> <path>    # Register project for bot access
weld telegram projects remove <name>        # Unregister project
weld telegram projects list                 # List registered projects

# Run bot
weld telegram serve                         # Start long-polling bot server
```

#### Telegram Bot Commands

Once `weld telegram serve` is running, users interact via Telegram:

- `/use [project]` - Switch project context (or show current)
- `/status` - Show queue and run status
- `/cancel` - Cancel active/pending runs
- `/doctor` - Run environment check on current project
- `/plan [spec.md]` - Generate implementation plan
- `/interview [spec.md]` - Interactive spec refinement
- `/implement <plan.md>` - Execute plan steps
- `/commit [-m msg]` - Commit changes with transcripts
- `/fetch <path>` - Download file from project
- `/push <path>` - Upload file to project (reply to document)

#### Configuration

Config file: `~/.config/weld/telegram.toml` (created by `weld telegram init`)

```toml
bot_token = "123456:ABC..."

[auth]
allowed_user_ids = [123456789]
allowed_usernames = ["myusername"]

[[projects]]
name = "myproject"
path = "/home/user/projects/myproject"
description = "My project"
```

State database: `~/.weld/telegram/state.db` (SQLite)

#### Security Model

- **Allowlist-only**: Bot ignores all messages from users not in `auth.allowed_user_ids` or `auth.allowed_usernames`
- **Token protection**: Config file set to `0o600` (owner read/write only)
- **Project isolation**: Commands execute in registered project directories only
- **No shell**: All subprocess calls use explicit argument lists (never `shell=True`)
- **Silent rejection**: Unauthorized access attempts are logged but receive no response

#### Installation

Telegram support is included in the standard weld installation. No additional setup required.

## Git Commits

- Never mention Claude Code in commit messages
- NEVER include the generated footer or Co-Authored-By trailer
- Use imperative mood ("Add feature" not "Added feature")
- Keep commits small and focused
- Update CHANGELOG.md before committing (use Keep a Changelog format with [Unreleased] section)
  - Only include user-facing changes (new features, bug fixes, breaking changes)
  - Exclude: test refactors, internal code changes, CI/build updates, documentation typos

## Code Quality

- Never bypass linting with exceptions unless explicitly requested
- Line length: 100 characters (pyproject.toml)
- Type hints required; pyright in standard mode
- Ruff for linting/formatting (ignores B008 for Typer pattern)
- Test markers: `@pytest.mark.unit`, `@pytest.mark.cli`, `@pytest.mark.slow`
- Coverage requirement: 70% (`make test-cov`)

## Testing Patterns

- Use `runner` fixture (CliRunner) for CLI tests with NO_COLOR=1
- Use `temp_git_repo` fixture for git-dependent tests (auto-configures user, creates initial commit)
- Subprocess safety: All external commands use `subprocess.run()` with `check=True`, `capture_output=True`, `timeout=N`
- Mock external CLIs (`claude`, `gh`) in unit tests; integration tests marked with `@pytest.mark.cli`

## Security Constraints

- NEVER use `shell=True` in subprocess calls
- All subprocess calls must include timeout parameter
- Services layer validates all external inputs before passing to subprocess
- Transcript rendering redacts secrets (API keys, tokens, credentials) via pattern matching
