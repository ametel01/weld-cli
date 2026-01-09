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
│   └── doctor.py       # weld doctor - Environment validation
├── core/               # Business logic
│   ├── history.py      # JSONL command history tracking
│   ├── weld_dir.py     # .weld directory utilities
│   ├── plan_parser.py  # Phased plan parsing (Phase, Step, Plan)
│   ├── discover_engine.py    # Codebase discovery prompts
│   ├── interview_engine.py   # Specification refinement prompts
│   └── doc_review_engine.py  # Document review prompts
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

### Configuration System

Config file: `.weld/config.toml` (TOML format, Pydantic validation)

Key sections:
- `[project]`: Project metadata
- `[checks]`: Multi-category checks (lint/test/typecheck with execution order)
- `[codex]` / `[claude]`: Provider defaults (exec path, model, timeout)
- `[task_models]`: Per-task model assignment (discover, plan_generation, implementation, etc.)
- `[transcripts]`: Transcript generation (enabled, visibility)
- `[git]`: Commit trailer configuration
- `[loop]`: Implement-review-fix loop settings

Config migration: Old `[claude.transcripts]` auto-migrates to top-level `[transcripts]`

## Git Commits

- Never mention Claude Code in commit messages
- Never include the generated footer or Co-Authored-By trailer
- Use imperative mood ("Add feature" not "Added feature")
- Keep commits small and focused
- Update CHANGELOG.md before committing (use Keep a Changelog format with [Unreleased] section)

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
