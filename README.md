<p align="center">
  <img src=".github/weld-logo.png" alt="Weld Logo" width="400">
</p>

**Human-in-the-loop coding harness with transcript provenance**

Weld generates structured prompts for AI-assisted development workflows. Instead of ad-hoc prompting, weld provides templates for: research → plan → implement → review → commit.

### Why Weld?

- **Structured Prompts**: Generate focused prompts for research, planning, and review
- **Full Auditability**: Every AI interaction linked via transcript gists in commits
- **Codebase Discovery**: Analyze existing codebases before making changes
- **Spec Refinement**: Interview-style Q&A to improve specifications

```
Spec Doc  -->  Research Prompt  -->  Plan Prompt  -->  Review  -->  Commit
                                                                  + transcript
```

## Table of Contents

- [Quickstart](#quickstart)
- [Installation](#installation)
- [Workflow Overview](#workflow-overview)
- [Commands Reference](#commands-reference)
- [Configuration](#configuration)
- [Developer Guide](#developer-guide)
- [Exit Codes](#exit-codes)
- [Requirements](#requirements)

---

## Quickstart

Get running in under 5 minutes:

```bash
# 1. Install weld globally
git clone <repo-url> && cd weld-cli
uv tool install .    # or: pipx install .

# 2. Initialize in your project
cd /path/to/your-project
weld init

# 3. Check your environment
weld doctor

# 4. Research a specification (generates prompt, runs Claude)
weld research specs/my-feature.md --output research.md

# 5. Generate a plan from your spec
weld plan specs/my-feature.md --output plan.md

# 6. Review a document against the codebase
weld review plan.md --apply

# 7. Commit with transcript provenance
weld commit -m "Implement feature" --staged
```

---

## Installation

### Prerequisites

- **Python 3.11+**
- **uv** or **pipx** - For global CLI installation
- **git** - Version control
- **gh** - GitHub CLI (authenticated)
- **claude** - Claude Code CLI (AI provider)
- **claude-code-transcripts** - For transcript gist generation (optional)

### Install Globally (Recommended)

Install weld as a global CLI tool so you can use it in any project:

```bash
# Option 1: Using uv (recommended)
git clone <repo-url> && cd weld-cli
uv tool install .

# Option 2: Using pipx
git clone <repo-url> && cd weld-cli
pipx install .

# Verify installation
weld --help
```

Now `weld` is available system-wide. Use it in any project:

```bash
cd /path/to/your-project
weld init
weld doctor
```

### Install for Development

For contributing to weld itself:

```bash
git clone <repo-url> && cd weld-cli
make setup
eval $(make venv-eval)

# weld is now available in this shell
weld --help
```

### Verify Toolchain

```bash
# Check all required dependencies
weld doctor
```

This validates:
- **Required**: `git`, `gh` (GitHub CLI authenticated)
- **Optional**: `claude`, `claude-code-transcripts`

---

## Workflow Overview

Weld provides prompts for a structured development workflow:

```
1. Discovery (optional)  | Analyze existing codebase architecture
2. Interview (optional)  | Refine specification through Q&A
3. Research              | Deep dive into implementation approach
4. Planning              | Generate step-by-step implementation plan
5. Review                | Validate documents against codebase
6. Commit                | Create commit with transcript link
```

### Key Concepts

- **Prompt Generation**: Weld creates structured prompts that you run in Claude Code
- **History Tracking**: Commands log their inputs/outputs to `.weld/<command>/history.jsonl`
- **Transcript**: A Claude Code session record, published as a GitHub gist and linked in commit messages

---

## Commands Reference

### Global Options

All commands support these global options:

| Option | Short | Description |
|--------|-------|-------------|
| `--version` | `-V` | Show version and exit |
| `--verbose` | `-v` | Increase verbosity (`-v` for verbose, `-vv` for debug) |
| `--quiet` | `-q` | Suppress non-error output |
| `--json` | | Output in JSON format for automation |
| `--no-color` | | Disable colored output |
| `--dry-run` | | Preview effects without applying changes |
| `--debug` | | Enable file-based debug logging to `.weld/debug.log` |

---

### `weld init`

Initialize weld in the current git repository.

```bash
weld init
```

Creates:
- `.weld/config.toml` - Configuration file

Exit codes:
- `0` - Success
- `2` - Missing or unauthenticated tool
- `3` - Not a git repository

---

### `weld plan <input> --output <path>`

Generate an implementation plan from a specification.

```bash
weld plan specs/feature.md --output plan.md
weld plan specs/feature.md -o plan.md --quiet  # Suppress streaming
```

Options:
- `--output`, `-o` - Path to write the plan (required)
- `--quiet`, `-q` - Suppress streaming output

The command:
1. Reads the specification file
2. Generates a planning prompt
3. Runs Claude to create the plan
4. Writes the result to the output file

---

### `weld research <input> --output <path>`

Research a specification before planning.

```bash
weld research specs/feature.md --output research.md
weld research specs/feature.md -o research.md --quiet
```

Options:
- `--output`, `-o` - Path to write research (required)
- `--quiet`, `-q` - Suppress streaming output

The research prompt guides Claude to analyze:
- Architecture and existing patterns
- Dependencies and integration points
- Risks and open questions

---

### `weld discover --output <path>`

Analyze codebase and generate architecture documentation.

```bash
weld discover --output docs/architecture.md
weld discover -o docs/arch.md --focus "authentication system"
weld discover --prompt-only  # Just show the prompt
```

Options:
- `--output`, `-o` - Path to write discover output (required unless --prompt-only)
- `--focus`, `-f` - Specific areas to focus on
- `--prompt-only` - Output prompt without running Claude
- `--quiet`, `-q` - Suppress streaming output

The discover prompt covers:
- High-level architecture
- Directory structure
- Key files and entry points
- Testing patterns
- Security considerations

---

### `weld discover show`

Show a previously generated discover prompt.

```bash
weld discover show
```

---

### `weld interview <file>`

Refine a specification through interactive Q&A.

```bash
weld interview specs/feature.md
weld interview specs/feature.md --focus "edge cases"
```

Options:
- `--focus`, `-f` - Topic to focus questions on

Outputs a prompt for Claude Code that:
1. Asks in-depth questions using the `AskUserQuestion` tool
2. Covers implementation, UI/UX, edge cases, tradeoffs
3. Rewrites the specification when complete

---

### `weld review <file> [--apply]`

Review a document against the codebase.

```bash
weld review plan.md                    # Show review prompt
weld review plan.md --apply            # Apply corrections in place
weld review research.md --prompt-only  # Just show the prompt
```

Options:
- `--apply` - Correct document in place (saves original to `.weld/reviews/`)
- `--prompt-only` - Output prompt without running Claude
- `--quiet`, `-q` - Suppress streaming output

Reviews check for:
- Errors and inaccuracies
- Missing implementations
- Gaps in coverage
- Wrong evaluations

---

### `weld commit -m "<message>" [--all] [--staged]`

Create a commit with transcript trailer.

```bash
weld commit -m "Implement user auth" --staged
weld commit -m "Implement user auth" --all
weld commit -m "Add feature" --skip-transcript
```

Options:
- `-m`, `--message` - Commit message (required)
- `--staged` (default) - Commit only staged changes
- `--all`, `-a` - Stage all changes before committing
- `--skip-transcript` - Skip transcript generation

The commit message includes a trailer:
```
Implement user auth

Claude-Transcript: https://gist.github.com/...
```

Exit codes:
- `0` - Committed
- `1` - Weld not initialized
- `20` - No changes to commit
- `21` - Transcript generation failed (warning only)
- `22` - Git commit failed

---

### `weld doctor`

Check environment and dependencies.

```bash
weld doctor
```

Validates:
- **Required tools**: git, gh (GitHub CLI)
- **Optional tools**: claude, claude-code-transcripts

Exit codes:
- `0` - All required dependencies available
- `2` - Required dependencies missing

---

## Configuration

Configuration lives in `.weld/config.toml`:

```toml
[project]
name = "your-project"

[claude]
exec = "claude"          # Claude CLI path
model = "claude-sonnet-4-20250514"  # Default model (optional)

[claude.transcripts]
exec = "claude-code-transcripts"
visibility = "secret"    # or "public"

[git]
commit_trailer_key = "Claude-Transcript"
```

---

## Developer Guide

### Architecture

Weld follows a simple layered architecture:

```
src/weld/
├── cli.py              # Typer app entry point, global options
├── config.py           # Configuration management
├── output.py           # Console output formatting
├── logging.py          # Logging configuration
├── validation.py       # Input validation
│
├── commands/           # CLI command modules
│   ├── init.py         # weld init
│   ├── plan.py         # weld plan
│   ├── research.py     # weld research
│   ├── discover.py     # weld discover
│   ├── interview.py    # weld interview
│   ├── doc_review.py   # weld review
│   ├── commit.py       # weld commit
│   └── doctor.py       # weld doctor
│
├── core/               # Business logic
│   ├── history.py      # JSONL command history tracking
│   ├── weld_dir.py     # .weld directory utilities
│   ├── discover_engine.py    # Codebase discovery prompts
│   ├── interview_engine.py   # Specification refinement
│   └── doc_review_engine.py  # Document review prompts
│
├── services/           # External integrations
│   ├── git.py          # Git operations
│   ├── claude.py       # Claude CLI integration
│   ├── transcripts.py  # Transcript gist generation
│   └── filesystem.py   # File system operations
│
└── models/             # Pydantic data models
    ├── discover.py     # DiscoverMeta
    └── issues.py       # Issue, Issues
```

### Key Design Patterns

- **Commands delegate to core**: `commands/*.py` handle CLI parsing, then call `core/*.py` for logic
- **Services wrap external CLIs**: All subprocess calls go through `services/` (never `shell=True`)
- **JSONL history**: Each command logs to `.weld/<command>/history.jsonl`

### Project Structure

```
weld-cli/
├── pyproject.toml      # Package configuration
├── Makefile            # Build automation
├── src/
│   └── weld/           # Main package
├── tests/              # Test suite
│   ├── conftest.py     # Pytest fixtures
│   ├── test_cli.py
│   ├── test_claude.py
│   ├── test_history.py
│   └── ...
└── .weld/              # Created per-project
    ├── config.toml
    ├── debug.log       # Debug log (with --debug)
    ├── plan/
    │   └── history.jsonl
    ├── research/
    │   └── history.jsonl
    ├── discover/
    │   └── history.jsonl
    └── reviews/        # Backup of reviewed docs
```

### Data Models

#### DiscoverMeta
Metadata for discover artifacts.

```python
class DiscoverMeta(BaseModel):
    discover_id: str
    created_at: datetime
    focus: list[str]
```

#### Issues
Review result from AI provider.

```python
class Issue(BaseModel):
    severity: Literal["blocker", "major", "minor"]
    file: str
    hint: str

class Issues(BaseModel):
    pass_: bool = Field(alias="pass")
    issues: list[Issue]
```

### Development Commands

```bash
# Essential commands
make setup          # First-time setup
make check          # All quality checks
make test           # Run tests
make ci             # Full CI pipeline

# Testing
make test-unit      # Unit tests only
make test-cli       # CLI integration tests
make test-cov       # Tests with coverage

# Code quality
make lint-fix       # Auto-fix linting
make format         # Format code
make typecheck      # Run pyright
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error / file not found / weld not initialized |
| 2 | Dependency missing / unauthenticated gh |
| 3 | Not a git repository |
| 12 | AI provider invocation failed |
| 20 | No changes to commit |
| 21 | Transcript generation failed |
| 22 | Git commit failed |

---

## Requirements

**For using weld:**
- Python 3.11+
- uv or pipx (for global installation)
- git
- gh (GitHub CLI, authenticated)
- claude (Claude Code CLI)

**Optional:**
- claude-code-transcripts (for transcript gist generation)

**For development:**
- make (build automation)
- uv (package manager)

---

## License

See [LICENSE](LICENSE) for details.
