# Weld

**Human-in-the-loop coding harness with transcript provenance**

Weld orchestrates AI-assisted development through a structured pipeline: plan, implement, review, iterate, and commit - with full auditability via Claude Code transcript links.

```
Spec Doc  -->  AI Plan  -->  AI Review  -->  Implementation Loop  -->  Commit
                                              (implement + review)       + transcript
```

## Table of Contents

- [Quickstart](#quickstart)
- [Installation](#installation)
- [Workflow Overview](#workflow-overview)
- [User Guide](#user-guide)
  - [Commands Reference](#commands-reference)
  - [Configuration](#configuration)
  - [Per-Task Model Selection](#per-task-model-selection)
  - [Plan Format](#plan-format)
- [Developer Guide](#developer-guide)
  - [Architecture](#architecture)
  - [Project Structure](#project-structure)
  - [Data Models](#data-models)
  - [Testing](#testing)
  - [Contributing](#contributing)
- [Exit Codes](#exit-codes)
- [Requirements](#requirements)

---

## Quickstart

Get running in under 5 minutes:

```bash
# 1. Clone and install
git clone <repo-url> && cd weld-cli
uv venv && uv pip install -e .

# 2. Initialize in your project
cd /path/to/your-project
weld init

# 3. Start a run from a spec file
weld run --spec specs/my-feature.md

# 4. Copy the prompt to Claude, save output as plan.md, then:
weld plan import --run <run_id> --file plan.md
weld plan review --run <run_id> --apply

# 5. Implement step by step
weld step loop --run <run_id> --n 1 --wait

# 6. Commit with transcript provenance
weld commit --run <run_id> -m "Implement step 1" --staged
```

---

## Installation

### Prerequisites

- **Python 3.14+** (or 3.11+ as per spec)
- **uv** - Python package manager (required)
- **git** - Version control
- **gh** - GitHub CLI (authenticated)
- **claude** - Claude Code CLI (AI provider)
- **codex** - OpenAI Codex CLI (AI provider, optional)
- **claude-code-transcripts** - For transcript gist generation

### Install with uv

```bash
# Create virtual environment
uv venv

# Install in editable mode
uv pip install -e .

# Install with dev dependencies
uv pip install -e ".[dev]"

# Verify installation
weld --help
```

### Verify Toolchain

```bash
# Initialize weld to check all dependencies
weld init
```

This validates:
- `git` is available
- `gh auth status` passes (GitHub CLI authenticated)
- `codex` is installed
- `claude-code-transcripts` is available

---

## Workflow Overview

Weld implements a deterministic, auditable development pipeline:

```
1. Plan Generation     | AI reads spec, creates step-by-step plan
2. Plan Review         | AI reviews/amends the plan
3. Step Implementation | Human implements with AI-generated prompts
4. Implementation Review | AI reviews diff against acceptance criteria
5. Fix Iteration       | Repeat 3-4 until review passes (or max iterations)
6. Commit              | Create commit with transcript link
```

### Key Concepts

- **Run**: A complete workflow session from spec to commit. Each run gets a unique ID like `20260104-120000-my-feature`.

- **Step**: An atomic unit of implementation from the plan. Each step has acceptance criteria and tests.

- **Iteration**: One cycle through implement-review-fix within a step.

- **Transcript**: A Claude Code session record, published as a GitHub gist and linked in commit messages.

---

## User Guide

### Commands Reference

#### `weld init`

Initialize weld in the current git repository.

```bash
weld init
```

Creates:
- `.weld/config.toml` - Configuration file
- `.weld/runs/` - Directory for run artifacts

Exit codes:
- `0` - Success
- `2` - Missing or unauthenticated tool
- `3` - Not a git repository

---

#### `weld run --spec <path>`

Start a new run from a specification file.

```bash
weld run --spec specs/feature.md
weld run --spec specs/feature.md --name my-feature  # Custom run ID slug
```

Creates:
- `.weld/runs/<run_id>/meta.json` - Run metadata
- `.weld/runs/<run_id>/inputs/spec.ref.json` - Spec file reference
- `.weld/runs/<run_id>/plan/plan.prompt.md` - Prompt for plan generation

Outputs the plan generation prompt to terminal for copy/paste to your AI.

---

#### `weld plan import --run <id> --file <path>`

Import an AI-generated plan.

```bash
weld plan import --run 20260104-120000-feature --file plan.md
```

Creates:
- `plan/output.md` - Verbatim AI output
- `plan/plan.raw.md` - Normalized plan

Parses steps using strict format first (`## Step N: Title`), falling back to lenient format (`N. Title`).

---

#### `weld plan review --run <id> [--apply]`

Review the plan with the configured AI provider.

```bash
weld plan review --run 20260104-120000-feature --apply
```

Options:
- `--apply` - Extract and save the revised plan to `plan/plan.final.md`

The reviewer outputs:
- `## Findings` - Issues and improvements
- `## Revised Plan` - Complete updated plan
- `## Risk Notes` - Implementation risks

---

#### `weld step select --run <id> --n <int>`

Select a step from the plan for implementation.

```bash
weld step select --run 20260104-120000-feature --n 1
```

Creates:
- `steps/01-<slug>/step.json` - Step metadata
- `steps/01-<slug>/prompt/impl.prompt.md` - Implementation prompt

---

#### `weld step loop --run <id> --n <int> [--wait] [--max <int>]`

Run the implement-review-fix loop for a step.

```bash
weld step loop --run 20260104-120000-feature --n 1 --wait
```

Options:
- `--wait`, `-w` - Pause for user input between iterations
- `--max`, `-m` - Override max iterations (default from config)

Each iteration:
1. Captures git diff
2. Runs checks command
3. AI reviews implementation
4. If issues found, generates fix prompt
5. Repeats until pass or max iterations

Exit codes:
- `0` - Step passed
- `10` - Max iterations reached

---

#### `weld step snapshot --run <id> --n <int> [--iter <int>]`

Manually capture diff and checks for an iteration.

```bash
weld step snapshot --run 20260104-120000-feature --n 1 --iter 2
```

---

#### `weld step review --run <id> --n <int> [--iter <int>]`

Manually run AI review on a step iteration.

```bash
weld step review --run 20260104-120000-feature --n 1 --iter 1
```

---

#### `weld step fix-prompt --run <id> --n <int> --iter <int>`

Generate a fix prompt for the next iteration.

```bash
weld step fix-prompt --run 20260104-120000-feature --n 1 --iter 1
```

---

#### `weld transcript gist --run <id>`

Generate a transcript gist for the run.

```bash
weld transcript gist --run 20260104-120000-feature
```

---

#### `weld commit --run <id> -m "<message>" [--all] [--staged]`

Create a commit with transcript trailer.

```bash
weld commit --run 20260104-120000-feature -m "Implement user auth" --staged
weld commit --run 20260104-120000-feature -m "Implement user auth" --all
```

Options:
- `--staged` (default) - Commit only staged changes
- `--all`, `-a` - Stage all changes before committing

The commit message includes trailers:
```
Implement user auth

Claude-Transcript: https://gist.github.com/...
Weld-Run: .weld/runs/20260104-120000-feature
```

Exit codes:
- `0` - Committed
- `20` - No changes to commit
- `21` - Transcript generation failed
- `22` - Git commit failed

---

#### `weld list`

List all runs.

```bash
weld list
```

---

### Configuration

Configuration lives in `.weld/config.toml`:

```toml
[project]
name = "your-project"

[checks]
# Command to validate implementation (runs from repo root)
command = "pytest && ruff check"

[codex]
exec = "codex"           # Codex executable path
sandbox = "read-only"    # Sandbox mode
model = "o3"             # Default model (optional)

[claude]
exec = "claude"          # Claude CLI path
model = "claude-3-opus"  # Default model (optional)

[claude.transcripts]
exec = "claude-code-transcripts"
visibility = "secret"    # or "public"

[git]
commit_trailer_key = "Claude-Transcript"
include_run_trailer = true

[loop]
max_iterations = 5
fail_on_blockers_only = true  # Pass if no blockers (ignore major/minor)

# Per-task model selection (see next section)
[task_models]
plan_generation = { provider = "claude" }
plan_review = { provider = "codex" }
implementation = { provider = "claude" }
implementation_review = { provider = "codex" }
fix_generation = { provider = "claude" }
```

---

### Per-Task Model Selection

Weld supports configuring different AI providers for each task type. Both Claude and Codex can be used interchangeably for any task.

| Task | Description |
|------|-------------|
| `plan_generation` | Create implementation plan from spec |
| `plan_review` | Review and improve the plan |
| `implementation` | Generate implementation prompts |
| `implementation_review` | Review diff against acceptance criteria |
| `fix_generation` | Generate fix prompts for issues |

#### Configuration Examples

**Use Claude for everything:**
```toml
[task_models]
plan_generation = { provider = "claude", model = "claude-3-opus" }
plan_review = { provider = "claude", model = "claude-3-opus" }
implementation = { provider = "claude" }
implementation_review = { provider = "claude" }
fix_generation = { provider = "claude" }
```

**Use specific models per task:**
```toml
[task_models]
plan_generation = { provider = "claude", model = "claude-3-opus" }
plan_review = { provider = "codex", model = "o3" }
implementation = { provider = "claude", model = "claude-3-sonnet" }
implementation_review = { provider = "openai", model = "gpt-4o" }
fix_generation = { provider = "claude" }
```

**Override executable path:**
```toml
[task_models]
plan_review = { provider = "codex", exec = "/custom/path/codex" }
```

#### Priority Order

1. Task-specific `model` field
2. Provider default (from `[codex]` or `[claude]` sections)
3. Tool default

---

### Plan Format

Weld expects plans in a structured markdown format:

#### Strict Format (Recommended)

```markdown
## Step 1: Create config module

### Goal
Set up configuration handling with TOML support.

### Changes
- Create `src/config.py`
- Add `tomli-w` dependency

### Acceptance criteria
- [ ] Config loads from TOML file
- [ ] Default values work when no config exists
- [ ] Invalid TOML raises clear error

### Tests
- pytest tests/test_config.py
- python -c "from myapp.config import load_config; print('OK')"

## Step 2: Build CLI
...
```

#### Lenient Format (Fallback)

If strict format isn't found, weld falls back to:

```markdown
1. Create config module
   Set up configuration handling.

2. Build CLI
   Create the CLI entry point.
```

---

## Developer Guide

### Architecture

Weld follows a modular architecture:

```
weld/
├── cli.py          # Typer CLI commands
├── config.py       # Configuration management
├── constants.py    # Timeout and other constants
├── run.py          # Run lifecycle management
├── plan.py         # Plan parsing and prompts
├── step.py         # Step management and prompts
├── loop.py         # Implement-review-fix loop
├── review.py       # AI review orchestration
├── commit.py       # Commit with transcripts
├── codex.py        # Codex CLI integration
├── claude.py       # Claude CLI integration
├── transcripts.py  # Transcript gist generation
├── git.py          # Git operations wrapper
├── diff.py         # Diff capture utilities
├── checks.py       # Checks command runner
├── validation.py   # Input validation utilities
└── models/         # Pydantic data models
    ├── meta.py     # Run metadata
    ├── step.py     # Step model
    ├── issues.py   # Review issues
    └── status.py   # Iteration status
```

### Project Structure

```
weld-cli/
├── pyproject.toml      # Package configuration
├── src/
│   └── weld/           # Main package
├── tests/              # Test suite
│   ├── test_claude.py
│   ├── test_codex.py
│   ├── test_config.py
│   ├── test_models.py
│   ├── test_plan.py
│   ├── test_run.py
│   └── test_validation.py
└── .weld/              # Created per-project
    ├── config.toml
    └── runs/
        └── <run_id>/
            ├── meta.json
            ├── inputs/
            │   └── spec.ref.json
            ├── plan/
            │   ├── plan.prompt.md
            │   ├── output.md
            │   ├── plan.raw.md
            │   ├── review.prompt.md
            │   ├── review.output.md
            │   └── plan.final.md
            ├── steps/
            │   └── 01-<slug>/
            │       ├── step.json
            │       ├── prompt/
            │       │   ├── impl.prompt.md
            │       │   └── fix.iter02.md
            │       └── iter/
            │           ├── 01/
            │           │   ├── diff.patch
            │           │   ├── checks.txt
            │           │   ├── review.md
            │           │   ├── issues.json
            │           │   └── status.json
            │           └── 02/...
            ├── commit/
            │   ├── message.txt
            │   └── transcript.json
            └── summary.md
```

### Data Models

#### Meta
Run metadata: timestamps, repo info, config hash.

```python
class Meta(BaseModel):
    run_id: str
    created_at: datetime
    repo_root: Path
    branch: str
    head_sha: str
    config_hash: str
```

#### Step
Parsed plan step with acceptance criteria.

```python
class Step(BaseModel):
    n: int
    title: str
    slug: str
    body_md: str
    acceptance_criteria: list[str]
    tests: list[str]
```

#### Issues
Review result from AI provider.

```python
class Issue(BaseModel):
    severity: Literal["blocker", "major", "minor"]
    file: str
    hint: str
    maps_to: str | None  # e.g., "AC #2"

class Issues(BaseModel):
    pass_: bool = Field(alias="pass")
    issues: list[Issue]
```

#### Status
Iteration status with counts.

```python
class Status(BaseModel):
    pass_: bool = Field(alias="pass")
    issue_count: int
    blocker_count: int
    major_count: int
    minor_count: int
    checks_exit_code: int
    diff_nonempty: bool
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=weld

# Run specific test file
pytest tests/test_models.py -v

# Lint code
ruff check src/weld

# Type check
mypy src/weld
```

### Contributing

1. **Fork and clone** the repository
2. **Create a virtual environment**: `uv venv && source .venv/bin/activate`
3. **Install in dev mode**: `uv pip install -e ".[dev]"`
4. **Make changes** with tests
5. **Run checks**: `pytest && ruff check && mypy src/weld`
6. **Submit a PR**

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error / file not found |
| 2 | Dependency missing / unauthenticated gh |
| 3 | Not a git repository |
| 10 | Max iterations reached |
| 11 | Checks failed (strict mode) |
| 12 | AI provider invocation failed / malformed JSON |
| 20 | No changes to commit |
| 21 | Transcript generation failed |
| 22 | Git commit failed |

---

## Requirements

- Python 3.14+ (3.11+ per spec)
- uv package manager
- git
- gh (GitHub CLI, authenticated)
- claude (Claude Code CLI)
- codex (OpenAI Codex CLI, optional)
- claude-code-transcripts

---

## License

See [LICENSE](LICENSE) for details.
