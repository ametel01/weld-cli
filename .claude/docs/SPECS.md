## Python harness spec: `weld` (research → plan → implement → review + transcript-linked commits) — **uv required**

### Philosophy

> "If agents are not onboarded with accurate context, they will fabricate."

Like the protagonist in Memento, without grounded memory, agents invent narratives. Weld combats this by enforcing a structured pipeline where each phase compresses truth into artifacts that constrain subsequent phases.

> "Bad plans produce dozens of bad lines of code. Bad research produces hundreds."

Research is highest-leverage. A solid research artifact dramatically constrains planning. A solid plan makes implementation mechanical.

---

### Greenfield vs Brownfield Workflows

Weld uses the **same workflow phases** (research → plan → implement) for both greenfield and brownfield projects. The difference lies in the entry point and spec origin:

**Greenfield Projects:**
- User must provide a spec document in advance
- No bootstrap/scaffolding offered by weld
- Spec content is not validated; any markdown is accepted
- Workflow: `spec.md` → `weld run --spec` → research → plan → implement

**Brownfield Projects:**
- Use `weld discover` to reverse-engineer codebase into architecture spec
- Discover analyzes source code structure and logic (not tests, not dependencies)
- Generated spec uses file:line references only (no code snippets)
- Workflow: `weld discover` → (optional interview) → `weld run --spec` → research → plan → implement

```
GREENFIELD WORKFLOW
───────────────────────────────────────────────────────────

  [User writes spec.md]
           │
           ▼
  ┌─────────────────┐     ┌─────────────────┐
  │ weld interview  │◄───►│   spec.md       │ (optional)
  │ --focus 'x'     │     │   refined       │
  └────────┬────────┘     └─────────────────┘
           │
           ▼
  ┌─────────────────┐
  │ weld run --spec │
  └────────┬────────┘
           │
           ▼
    research → plan → implement → commit

───────────────────────────────────────────────────────────

BROWNFIELD WORKFLOW
───────────────────────────────────────────────────────────

  ┌─────────────────┐
  │ weld discover   │ ─── Analyzes entire codebase
  └────────┬────────┘     (chunked for large repos)
           │
           ▼
  ┌─────────────────┐     ┌─────────────────┐
  │ Refine spec?    │────►│ weld interview  │ (optional)
  │    [y/n]        │     │ architecture.md │
  └────────┬────────┘     └────────┬────────┘
           │                       │
           └───────────┬───────────┘
                       ▼
  ┌─────────────────────────────────┐
  │ User writes feature-spec.md    │
  │ (references architecture.md)   │
  └────────────────┬────────────────┘
                   │
                   ▼
  ┌─────────────────┐
  │ weld run --spec │ ─── feature-spec.md
  └────────┬────────┘
           │
           ▼
    research → plan → implement → commit

───────────────────────────────────────────────────────────
```

**Phase-by-phase execution:** Each phase requires explicit user commands. No automated research→plan→implement flow.

---

### Context Management

**Per-command context clearing:** Each weld command invocation starts with fresh context. When continuing from partial AI output (after timeout), the partial content is included but compacted to maintain high-quality context. This ensures agents always work with accurate, relevant information rather than accumulating stale context across operations.

---

### Workflow Stages

#### 1. Research: Compressing Truth

**Goal:** Understand how the system actually works

**Input:** Spec file (MD)
**Output:** Research artifact (MD)

**Characteristics:**
- Read code, not docs
- Identify authoritative files and flows
- Eliminate assumptions
- Validate findings manually

**Artifact contents:**
- Executive summary
- Authoritative files with purpose and key exports
- System flows with file:line references and code snippets
- Implementation patterns from the codebase
- Assumptions validated/invalidated with verification locations
- Extension points

**Revision support:** Research artifacts can be revised after review. See [Artifact Versioning](#artifact-versioning).

---

#### 2. Plan: Compressing Intent

**Goal:** Translate research into exact implementation steps

**Input:** Research artifact (MD) — or spec directly in skip-research mode
**Output:** Plan artifact (MD)

**A good plan:**
- Lists exact steps
- References concrete files and snippets
- Specifies validation after each change
- Makes failure modes obvious

**Plan format (strict):**
```markdown
## Step N: <Title>

### Goal
Brief description of what this step accomplishes.

### Changes
- List of files to create/modify
- Specific changes to make

### Acceptance criteria
- [ ] Criterion 1
- [ ] Criterion 2

### Tests
- Commands to verify the step works
```

**Skip-research mode:** For simpler tasks, `weld run --skip-research` generates a plan directly from the spec using a dedicated template that includes discovery directives. See [Direct Planning](#direct-planning-skip-research).

---

#### 3. Implement: Mechanical Execution

**Goal:** Execute plan steps with minimal context

**Input:** Plan artifact (MD) + step number
**Output:** Code changes + iteration artifacts

**Characteristics:**
- Execution becomes mechanical
- Context remains small
- Reliability increases
- This is where token spend pays off

**Loop per step:**
1. Generate implementation prompt from step
2. Capture diff + run checks
3. Run review
4. If issues: generate fix prompt, iterate
5. When passed: ready for commit

**Resume support:** If the loop fails at max iterations or is interrupted, `weld step loop --resume` continues from the last iteration.

---

#### 4. Review: Manual Verification

**Goal:** Human verification at any stage

**Can be performed on:**
- Research artifact (verify findings against code)
- Plan artifact (verify steps are complete and correct)
- Implementation (verify changes match plan)

**Review is always optional and manual** - the user decides when to invoke review and with which provider.

---

### Key Principles

* **Each step produces an MD artifact** - inspectable, versionable, shareable
* **Each step can be run independently** - user imports artifact, runs single command
* **No hardcoded AI providers** - user configures which model handles each task type
* **Human-in-the-loop** - hybrid AI invocation by default, manual mode available
* **Full provenance** - every run writes artifacts under `.weld/runs/<run_id>/`
* **Artifact lineage** - downstream artifacts track which upstream version they came from
* **Global dry-run** - any command supports `--dry-run` to preview effects

---

## Hard requirements

* Python **3.11+**
* Package manager: **`uv` only** (strict requirement)

  * No pip/poetry/pipenv workflows in docs or tooling
* Build backend: **`hatchling`**
* External CLIs available in PATH:

  * `git`
  * `gh` (GitHub CLI) authenticated
  * `codex` (OpenAI Codex CLI)
  * `claude-code-transcripts` (for transcript → gist)

---

## Discover Runs

Discovery runs are stored separately from implementation runs and produce architecture specs from codebase analysis.

### Storage Location

```
.weld/
  discover/
    <discover_id>/
      meta.json           # Timestamp, config hash, output path
      spec.md             # Generated architecture spec (copy)
```

### Version Retention

- Keep last 3 discover versions (auto-prune older)
- Each discover creates new entry; no in-place update
- Lineage tracked bi-directionally with implementation runs

### Lineage Tracking

When implementation run uses spec from discover:

**In discover meta.json:**
```json
{
  "used_by_runs": ["20240115-103000-feature"]
}
```

**In implementation run's spec.ref.json:**
```json
{
  "source_discover_id": "20240115-090000-discover"
}
```

---

## File Ignore Patterns (.weldignore)

Weld supports gitignore-style patterns to exclude files from analysis.

### Location

`.weldignore` in repository root (created via `weld init` prompt)

### Scope

Applies to **all phases**: discover, research, and plan generation.

### Default Content

When created, weld detects project type and includes language-specific defaults:

**Python projects:**
```
__pycache__/
*.pyc
*.pyo
.venv/
venv/
.eggs/
*.egg-info/
dist/
build/
.git/
.weld/
```

**Node.js projects:**
```
node_modules/
dist/
build/
.git/
.weld/
```

---

## Repository layout (created/managed by `weld`)

```
repo/
  pyproject.toml
  .python-version
  .weldignore                     # File ignore patterns (gitignore-style)
  .weld/
    config.toml
    active.lock                   # PID-based run lock (when active)
    debug.log                     # Debug log (if enabled)
    discover/                     # Discover run artifacts
      <discover_id>/
        meta.json                 # Timestamp, config hash, output path, lineage
        spec.md                   # Copy of generated architecture spec
    templates/                    # User-customized prompt templates (optional)
      research.prompt.md
      plan.prompt.md
      plan.direct.prompt.md       # For skip-research mode
      impl.prompt.md
      fix.prompt.md
      review.prompt.md
    runs/
      <run_id>/
        meta.json
        inputs/
          spec.ref.json               # Reference to input spec file
        research/
          prompt.md                   # Prompt for research generation
          research.md                 # Research artifact (current version)
          history/                    # Version history
            v1/
              content.md
              meta.json               # timestamp, review_id, trigger_reason
            v2/...
          review.prompt.md            # Review prompt (if reviewed)
          review.md                   # Review output (if reviewed)
        plan/
          prompt.md                   # Prompt for plan generation (from research)
          plan.md                     # Plan artifact (current version)
          history/                    # Version history
            v1/
              content.md
              meta.json
            v2/...
          review.prompt.md            # Review prompt (if reviewed)
          review.md                   # Review output (if reviewed)
        steps/
          01-<slug>/
            step.json
            prompt/
              impl.prompt.md          # Implementation prompt from step
              fix.iter<NN>.md         # Fix prompts for iterations 2+
            iter/
              01/
                diff.patch
                checks/               # Per-category check results
                  lint.txt
                  test.txt
                  typecheck.txt
                checks.summary.json   # Aggregated check status
                review.md             # Review output
                issues.json           # Parsed issues JSON
                status.json           # Iteration status
                timing.json           # Per-phase timing (AI, checks, review)
                partial.md            # Partial AI output (on timeout)
              02/...
            iter-amend/               # Amend iterations (if step reopened)
              01/...
        commit/
          transcript.json
          message.txt
        summary.md
  src/
    weld/
      __init__.py
      cli.py
      config.py
      constants.py
      logging.py
      output.py
      validation.py
      commands/
        __init__.py
        init.py
        run.py
        discover.py
        interview.py
        research.py
        plan.py
        step.py
        commit.py
        doctor.py
        status.py
      core/
        __init__.py
        run_manager.py
        discover_engine.py          # Codebase analysis and spec generation
        interview_engine.py         # Interactive Q&A session management
        research_processor.py
        plan_parser.py
        step_processor.py
        review_engine.py
        loop.py
        commit_handler.py
        lock_manager.py
        artifact_versioning.py
        ignore_patterns.py          # .weldignore parsing and matching
      services/
        __init__.py
        git.py
        codex.py
        claude.py
        transcripts.py
        checks.py
        diff.py
        filesystem.py
      models/
        __init__.py
        meta.py
        step.py
        issues.py
        status.py
        lock.py
        version_info.py
```

---

## Installation and execution (uv-only)

### Create environment and install editable

```bash
uv venv
uv pip install -e .
```

### Run

```bash
weld init
weld run --spec specs/horizon.md
```

---

## `pyproject.toml` (uv-native with hatchling)

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "weld"
version = "0.1.0"
description = "Human-in-the-loop coding harness: plan, review, iterate, commit with transcript provenance"
license = "Apache-2.0"
requires-python = ">=3.11"
dependencies = [
  "typer>=0.12",
  "pydantic>=2.6",
  "rich>=13.7",
  "tomli-w>=1.0",
]

[project.scripts]
weld = "weld.cli:app"

[dependency-groups]
dev = [
  "pytest>=8",
  "pytest-cov>=5.0",
  "hypothesis>=6.100",
  "ruff>=0.5",
  "pyright>=1.1",
  "pre-commit>=3.7",
  "pip-audit>=2.7",
  "detect-secrets>=1.5",
]

[tool.hatch.build.targets.wheel]
packages = ["src/weld"]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.pyright]
typeCheckingMode = "standard"
pythonVersion = "3.11"
```

---

## Configuration (`.weld/config.toml`)

### Full configuration schema

```toml
[project]
name = "your-project"

# Multi-category checks (fail-fast during iteration, all run for review)
[checks]
lint = "ruff check ."
test = "pytest tests/"
typecheck = "pyright"
# Order determines execution sequence; first failure stops iteration
order = ["lint", "typecheck", "test"]

[codex]
exec = "codex"
sandbox = "read-only"
# model = "..."   # optional - default model for Codex provider

[claude]
exec = "claude"
# model = "..."   # optional - default model for Claude provider
[claude.transcripts]
exec = "claude-code-transcripts"
visibility = "secret"  # or "public"

[git]
commit_trailer_key = "Claude-Transcript"
include_run_trailer = true

[loop]
max_iterations = 5
fail_on_blockers_only = true

[invoke]
mode = "hybrid"  # "hybrid" (default), "manual"
max_parse_retries = 1  # Auto-retry on parse failure

[debug]
log = false  # Enable persistent debug logging

[prompts]
# Custom templates directory (optional, defaults to built-in)
# templates_dir = ".weld/templates"

# Per-task model selection: customize which AI handles each task
# Provider can be "codex", "claude", or any other supported provider
# Model is optional and overrides the provider default
[task_models]
discover = { provider = "claude" }
interview = { provider = "claude" }
research = { provider = "claude" }
research_review = { provider = "codex" }
plan = { provider = "claude" }
plan_review = { provider = "codex" }
implementation = { provider = "claude" }
implementation_review = { provider = "codex" }
fix = { provider = "claude" }

# Discover-specific settings
[discover]
max_versions = 3  # Auto-prune to keep last N discover versions
```

### Task Types

Weld supports per-task model routing through `TaskType` enum:

- `discover` - Generating architecture spec from codebase (default: claude)
- `interview` - Interactive Q&A refinement (default: claude)
- `research` - Generating research artifact from spec (default: claude)
- `research_review` - Reviewing research artifact (default: codex)
- `plan` - Generating plan from research (default: claude)
- `plan_review` - Reviewing plan (default: codex)
- `implementation` - Implementing steps (default: claude)
- `implementation_review` - Reviewing implementations (default: codex)
- `fix` - Generating fix prompts (default: claude)

Each task can specify a `provider`, optional `model`, and optional `exec` path override.

**Note:** Defaults are examples only - user should configure based on their preference. Any provider can be used for any task.

### Notes

* Check commands are parsed via `shlex.split()` and executed without shell (no `shell=True`)
* `codex.sandbox=read-only` ensures Codex only reviews
* Credentials are validated lazily when each provider is first invoked

---

## Multi-Category Checks

Weld supports multiple check categories with fail-fast semantics during iteration but runs all checks for review context.

### Check Categories

Configure named check commands in `[checks]`:

```toml
[checks]
lint = "ruff check ."
test = "pytest tests/ -q"
typecheck = "pyright"
order = ["lint", "typecheck", "test"]
```

### Iteration Behavior (Fail-Fast)

During `weld step loop`, checks run in order and stop at first failure:
1. Run lint → if fails, stop
2. Run typecheck → if fails, stop
3. Run test → if fails, stop

This provides fast feedback without waiting for slow tests when quick checks fail.

### Review Behavior (Run All)

Even when fail-fast stops iteration, review receives results from all check categories:
- Failed categories show actual output
- Skipped categories (due to fail-fast) are run silently for review input
- Review prompt includes complete check status across all categories

### Output Format

`checks.summary.json`:
```json
{
  "categories": {
    "lint": {"exit_code": 0, "passed": true},
    "typecheck": {"exit_code": 0, "passed": true},
    "test": {"exit_code": 1, "passed": false}
  },
  "first_failure": "test",
  "all_passed": false
}
```

Individual category output in `checks/<category>.txt`.

---

## Artifact Versioning

Research and plan artifacts support revision with version history tracking.

### Version Storage

When an artifact is revised (imported after review), the previous version is archived:

```
research/
  research.md           # Current version (v2)
  history/
    v1/
      content.md        # Previous content
      meta.json         # Version metadata
    v2/
      content.md
      meta.json
```

### Version Metadata

`history/v1/meta.json`:
```json
{
  "version": 1,
  "created_at": "2024-01-15T10:30:00Z",
  "review_id": "review-001",
  "trigger_reason": "review identified missing integration points",
  "superseded_at": "2024-01-15T11:45:00Z"
}
```

### Lineage Tracking and Invalidation

Downstream artifacts track which upstream version they came from:

`plan/plan.md` header or `meta.json`:
```json
{
  "derived_from": {
    "artifact": "research",
    "version": 2
  }
}
```

**Stale artifact handling:** When research is updated to v3, plan derived from v2 is marked **stale**:
- Plan file remains but `meta.json` gains `"stale": true, "stale_reason": "research updated to v3"`
- Commands that depend on plan prompt for confirmation: `'Artifact is stale, proceed anyway? [y/N]'`
- If user proceeds despite staleness, decision is logged to `meta.json` with timestamp and artifact names for audit trail
- Regenerating from new research is recommended but not enforced

---

## Direct Planning (Skip-Research)

For smaller tasks where research is overkill, weld supports direct planning from spec.

### Command

```bash
weld run --spec specs/simple-feature.md --skip-research
```

### Behavior

1. Creates run directory without `research/` subdirectory
2. Generates plan prompt using dedicated `plan.direct.prompt.md` template
3. Direct plan template includes:
   - Directive to read relevant codebase files before planning
   - Discovery questions typically answered by research
   - Emphasis on identifying extension points and patterns

### Template Location

Default: Built-in `plan.direct.prompt.md`
Custom: `.weld/templates/plan.direct.prompt.md` (created via `weld init --customize`)

---

## Run Locking

Weld prevents concurrent runs to avoid conflicts.

### Lock Mechanism

When a run-modifying command starts, weld creates `.weld/active.lock`:

```json
{
  "pid": 12345,
  "run_id": "20240115-103000-feature",
  "command": "step loop --n 1",
  "started_at": "2024-01-15T10:30:00Z",
  "last_heartbeat": "2024-01-15T10:35:00Z"
}
```

### Stale Lock Detection (PID-Based)

On startup, weld checks if the lock PID is still running:
- If process is dead: lock is cleared and message displayed: `'Cleared stale lock from previous session'`
- If process is alive: command fails with "Run already in progress" error

### Lock Scope

Lock is acquired for:
- `weld run` (creating new run)
- `weld research import`, `weld plan import`
- `weld step loop`, `weld step amend`
- `weld commit`

Lock is NOT required for:
- `weld status`, `weld list`, `weld doctor`
- Read-only prompt generation commands

---

## AI Invocation Modes

Weld supports hybrid (default) and manual AI invocation modes.

### Hybrid Mode (Default)

Weld directly invokes the configured AI provider and captures output:

```bash
weld step loop --run <run_id> --n 1
# AI is invoked automatically, output captured
```

**Error handling:**
- On rate limit or transient error: Interactive prompt "Retry in 60s? [Y/n]"
- On parse failure: One automatic retry with "please format correctly" follow-up
- On timeout: Partial output saved to `iter/<n>/partial.md`, user prompted "Continue from partial? [Y/n]"

### Manual Mode

For explicit control, use `--manual` flag:

```bash
weld step loop --run <run_id> --n 1 --manual
```

**Behavior:**
1. Displays implementation prompt
2. Waits interactively: "Press Enter when AI output is ready, then paste..."
3. Captures pasted content
4. **Validation:** If pasted content has suspicious format, show warning but continue processing (let downstream commands handle errors)
5. Proceeds with review

Global manual mode via config:
```toml
[invoke]
mode = "manual"
```

### Wait Mode

For reviewing prompts before AI invocation, use `--wait` flag:

```bash
weld step loop --run <run_id> --n 1 --wait
```

**Behavior:**
1. Displays implementation prompt content
2. Shows: `'Press Enter to invoke AI...'`
3. On Enter: proceeds with normal AI invocation

**Distinction from --manual:**
- `--wait`: Pauses before AI invocation for prompt review, then invokes AI automatically
- `--manual`: Skips AI invocation entirely, user pastes output manually

---

## Loop Resume and Step Amend

### Resume After Failure

If `step loop` fails at max iterations or is interrupted:

```bash
weld step loop --run <run_id> --n 1 --resume
```

**Behavior:**
- Detects last iteration number from existing `iter/<n>/` directories
- Continues from iteration n+1 without resetting state
- Preserves all previous iteration artifacts

### Step Amend (Reopen Completed Step)

When a step passes review but issues are discovered post-commit:

```bash
weld step amend --run <run_id> --n 1
```

**Behavior:**
1. Creates `iter-amend/` directory for new iteration series
2. Links to original iteration history (full audit trail visible)
3. Runs normal loop in `iter-amend/01/`, `iter-amend/02/`, etc.
4. On completion, creates **fixup commit** (not `--amend`) referencing original

**Fixup commit format:**
```
fixup: <original commit subject>

Fixes issues in <original commit SHA>
<commit_trailer_key>: <gist_url>
Weld-Run: .weld/runs/<run_id>
```

---

## Run Continuation

Resume an incomplete run after interruption:

```bash
weld run --continue <run_id>
```

**Behavior:**
1. Detects last successful stage from run artifacts
2. Prompts for next action based on state:
   - Research exists, no plan → "Generate plan prompt?"
   - Plan exists, no steps started → "Select step?"
   - Step in progress → "Resume step loop?"
3. User confirms, weld executes appropriate command

---

## Subprocess Timeouts

All subprocess operations have configurable timeouts defined in `constants.py`:

| Constant | Default | Purpose |
|----------|---------|---------|
| `GIT_TIMEOUT` | 30s | Git commands (rev-parse, diff, commit) |
| `CODEX_TIMEOUT` | 600s (10 min) | Codex CLI invocations |
| `CLAUDE_TIMEOUT` | 600s (10 min) | Claude CLI invocations |
| `TRANSCRIPT_TIMEOUT` | 60s | Transcript gist generation |
| `CHECKS_TIMEOUT` | 300s (5 min) | Running checks command |
| `INIT_TOOL_CHECK_TIMEOUT` | 10s | Tool availability checks during init |

---

## CLI contract

### Global Options

```bash
weld [OPTIONS] COMMAND [ARGS]
```

Global options:
* `--version`, `-V` - Show version and exit
* `--verbose`, `-v` - Increase verbosity (can be stacked: -v, -vv)
* `--quiet`, `-q` - Suppress non-error output
* `--json` - Output in JSON format for automation (includes `schema_version` field)
* `--no-color` - Disable colored output
* `--dry-run` - Preview effects without applying (available on all commands)
* `--debug` - Enable debug logging for this invocation

---

### `weld init [--customize] [--reset-templates]`

* Creates `.weld/config.toml` template if missing
* Creates `.weld/runs/` and `.weld/discover/` directories
* **Nested weld detection:** If parent directory has `.weld/`, shows warning and asks to confirm
* **Ignore file prompt:** If `.weldignore` missing, prompts: `'Create .weldignore? [y/N]'`
  - If yes, detects project type and creates language-specific defaults
* Validates toolchain:

  * `git --version`
  * `gh auth status`
  * `codex --version`
  * `claude-code-transcripts --help`

**`--customize` flag:**
* Copies built-in prompt templates to `.weld/templates/`
* User can edit templates for project-specific customization

**`--reset-templates` flag:**
* Overwrites custom templates with built-in defaults
* Useful when customization goes wrong

Exit codes:

* `0` ok
* `2` dependency missing / unauthenticated `gh`
* `3` not a git repo

---

### `weld doctor`

Comprehensive diagnostic command for troubleshooting.

**Checks performed:**
- Tool availability (git, gh, codex, claude, transcripts)
- Tool authentication status (gh auth, API keys)
- Config file validity and schema compliance
- Provider connectivity (optional ping to configured providers)
- Run directory permissions
- Lock file status

**Output:**
```
[OK] git: 2.43.0
[OK] gh: authenticated as @user
[WARN] codex: version 0.9.0 (minimum recommended: 1.0.0)
[OK] claude: available
[OK] config: valid
[FAIL] provider connectivity: codex API unreachable
```

**Auto-fix for safe issues:**
For non-sensitive issues (e.g., missing directories), doctor offers to fix:
```
[FAIL] runs directory missing
  Fix: Run `mkdir -p .weld/runs`? [y/N]
```

**Note:** Auth-related fixes (like `gh auth login`) are NOT offered automatically - users must run these manually for security.

Exit codes:
* `0` all checks passed
* `1` one or more checks failed

---

## Discover Commands

### `weld discover [--output <path>]`

Analyzes the entire codebase to generate an architecture specification. This reverse-engineers the code into documentation.

**Purpose:** Brownfield projects use this to create a comprehensive understanding of existing code before implementing new features.

**Behavior:**

1. If `--output` not provided, prompts for output path
2. Respects `.weldignore` patterns
3. Analyzes source code structure and logic (excludes tests, dependencies)
4. For large codebases: uses chunked analysis (hidden from user)
5. Generates free-form markdown architecture spec with file:line references (no code snippets)
6. Creates discover run in `.weld/discover/<discover_id>/`
7. Auto-prunes to keep last 3 discover versions
8. After generation, prompts: `'Refine this spec? [y/n]'` (no default)
9. If yes, launches interview on the generated spec

**Multi-language support:** Analyzes all languages in the codebase.

**Timeout handling:** On timeout, saves partial analysis. User can review partial output.

**Lineage tracking:** When spec from discover is used in `weld run --spec`, bi-directional links are created.

Writes:
* User-specified output path (e.g., `architecture.md`)
* `.weld/discover/<discover_id>/meta.json`
* `.weld/discover/<discover_id>/spec.md` (copy)

Exit codes:
* `0` success
* `1` no source files found
* `12` AI invocation failed
* `13` timeout (partial saved)

---

### `weld interview <file> [--focus <topic>]`

Interactive Q&A session to refine any markdown document (spec, research, plan, architecture).

**Purpose:** Clarify requirements, fill gaps, and improve document completeness through guided questioning.

**Behavior:**

1. Reads the specified file (any accessible path, not limited to repo)
2. If `--focus` provided, all questions stay within that topic area (session-wide)
3. If `--focus` omitted, AI infers appropriate questions from file content
4. Questions asked one at a time; AI adapts based on previous answers (interactive mode)
5. Contradiction detection: If answer contradicts earlier response, pauses immediately for clarification
6. Questions focus on requirements (what), not implementation approach (how)
7. Continues until AI determines file is sufficiently detailed (no fixed limit)
8. Shows summary of changes before saving
9. Updates file in-place (no backup; user has git)
10. Each session starts fresh (no memory of previous sessions)

**File scope:** Works on any markdown file path, not limited to repository.

Exit codes:
* `0` success
* `1` file not found
* `2` user cancelled

---

### `weld status [--watch]`

Full dashboard showing current run state. **Static snapshot** - shows current state without live polling.

**Output includes:**
- Active run ID and lock status
- Current stage: research → plan → implement
- If implementing: current step, iteration number, last result
- Pending actions (what command to run next) as plain text to copy
- Progress indicator: `[x] research [x] plan [ ] step 1 [ ] step 2`

**Progress events:**
During long-running AI invocations, weld emits progress to stderr with animated spinner:
```
⠋ Waiting for AI (45s)...
```

Exit codes:
* `0` success
* `3` not a git repo

---

### `weld config validate`

Validates `.weld/config.toml` configuration file.

**Validation levels:**
- TOML syntax validity
- Schema compliance (expected keys, types, structure)
- Path verification (referenced templates, exec paths exist)

**Output:**
```
[OK] Syntax valid
[OK] Schema valid
[WARN] Template path .weld/templates/custom.md not found
[OK] Exec path 'codex' found in PATH
```

Exit codes:
* `0` configuration valid
* `1` validation errors found

---

### `weld run --spec <path> [--name <slug>] [--skip-research]`

Creates a new run directory and generates initial prompt.

**Lock acquisition:** Acquires run lock; fails if another run is active.

Writes:

* `.weld/runs/<run_id>/meta.json` (timestamps, repo root, branch, HEAD sha, config hash)
* `inputs/spec.ref.json` (absolute path, sha256, size)
* `research/prompt.md` (prompt to generate research artifact from spec) — OR
* `plan/prompt.md` (if `--skip-research`)

Prints to terminal:

* Path to prompt file
* The prompt contents (or invokes AI in hybrid mode)
* Configured target model for task

`run_id` format:

* `YYYYMMDD-HHMMSS-<slug>` (slug defaults to sanitized spec basename, max 50 chars)

Slug sanitization: lowercase, replace non-alphanumeric with hyphens, strip leading/trailing hyphens

---

### `weld run --continue <run_id>`

Resume an incomplete run from its last successful stage.

**Behavior:**
1. Load run state from artifacts
2. Determine next action based on what exists
3. Prompt user for confirmation
4. Execute appropriate command

---

### `weld run abandon --run <run_id>`

Mark a run as abandoned (soft delete).

**Behavior:**
1. Sets `"abandoned": true` in `meta.json` with timestamp
2. Run artifacts are preserved for reference
3. Abandoned runs are hidden from `weld list` by default

Exit codes:
* `0` run abandoned
* `1` run not found

---

### `weld run report --run <run_id>`

Generate a markdown summary report for a run.

**Report contents (summary only):**
- Run ID and timestamps
- Spec file reference
- Steps completed/skipped/failed
- Final status

Writes:
* `summary.md` in run directory

Exit codes:
* `0` report generated
* `1` run not found

---

### `weld run history --run <run_id>`

View command execution history for a run.

**Output format:**
```
2024-01-15 10:30:00  weld run --spec specs/feature.md
2024-01-15 10:35:00  weld research import --file research.md
2024-01-15 10:45:00  weld plan prompt
...
```

Shows timestamp + command invoked (no outcomes or durations).

Exit codes:
* `0` success
* `1` run not found

---

## Research Commands

### `weld research import --run <run_id> --file <research_md>`

Imports research artifact (MD file).

**If research already exists:**
- Current version moved to `history/v<n>/`
- Metadata recorded (timestamp, trigger reason)
- **Downstream artifacts marked stale** (plan invalidated)

Writes:

* `research/research.md` (the research artifact)
* `research/history/v<n>/` (if revising)

Updates:
* `meta.json` with timestamp and version info

---

### `weld research review --run <run_id>`

Runs configured provider to review research artifact.

Writes:

* `research/review.prompt.md` (review prompt)
* `research/review.md` (review output)

**Post-review revision prompt:**
After displaying review, prompts: `'Generate revised artifact? [y/N]'`
- If yes: Automatically invokes AI with revision prompt
- Shows generated revision and asks: `'Import this revision? [Y/n]'`
- If approved: Imports and versions the artifact

Exit codes:

* `0` success
* `1` run not found or no research imported
* `12` provider invocation failed

---

### `weld research prompt --run <run_id>`

Regenerates the research prompt (useful if spec changed).

Writes:

* `research/prompt.md`

---

## Plan Commands

### `weld plan prompt --run <run_id>`

Generates plan prompt from research artifact.

**Prerequisite:** Research must exist and not be stale.

Writes:

* `plan/prompt.md` (prompt to generate plan from research)

Records lineage:
* `meta.json` includes `derived_from: {artifact: "research", version: N}`

Prints to terminal:

* Path to `plan/prompt.md`
* The prompt contents (or invokes AI in hybrid mode)
* Configured target model for plan task

Exit codes:

* `0` success
* `1` run not found or no research artifact
* `4` research is stale (needs regeneration)

---

### `weld plan import --run <run_id> --file <plan_md>`

Imports plan artifact (MD file).

**If plan already exists:**
- Current version moved to `history/v<n>/`
- **Downstream artifacts marked stale** (selected steps invalidated)

Writes:

* `plan/plan.md` (the plan artifact)
* `plan/history/v<n>/` (if revising)

Updates:
* `meta.json` with `plan_parse_warnings` list

Normalization:

* Attempts strict parsing first (`## Step N: Title`)
* Falls back to lenient parsing (`N. Title`)
* Records warnings if no strict steps found or no steps at all

---

### `weld plan review --run <run_id>`

Runs configured provider to review plan artifact.

Writes:

* `plan/review.prompt.md` (review prompt)
* `plan/review.md` (review output)

**Post-review revision prompt:**
After displaying review, prompts: `'Generate revised artifact? [y/N]'`
- If yes: Automatically invokes AI with revision prompt
- Shows generated revision and asks: `'Import this revision? [Y/n]'`
- If approved: Imports and versions the artifact

Exit codes:

* `0` success
* `1` run not found or no plan imported
* `12` provider invocation failed

---

## Step Commands

### `weld step skip --run <run_id> --n <int> [--reason <text>]`

Skip a step in the plan (will not be implemented in this run).

**Behavior:**
1. Marks step as skipped in `step.json` with optional reason
2. Step cannot be unskipped - skip is final for this run
3. Skipped steps are excluded from `weld step loop --all`

**Reason parameter:** Optional; if omitted, defaults to empty string.

Exit codes:
* `0` step skipped
* `1` step not found or already completed

---

### `weld step select --run <run_id> --n <int>`

Selects step N from `plan/plan.md`.

**Prerequisite:** Plan must exist and not be stale.

Writes:

* `steps/<NN>-<slug>/step.json`
* `steps/<NN>-<slug>/prompt/impl.prompt.md`

Step extraction - **strict format** (preferred):

```markdown
## Step N: <Title>

### Goal
Brief description

### Changes
- File changes list

### Acceptance criteria
- [ ] Criterion 1
- [ ] Criterion 2

### Tests
- Test commands
```

**Lenient fallback**:

* Step begins with `N.` at start of line
* Continues until next `^\d+\.` pattern
* No structured extraction of criteria/tests

`step.json` structure:

```json
{
  "n": 1,
  "title": "Step title",
  "slug": "step-title",
  "body_md": "Full markdown content",
  "acceptance_criteria": ["Criterion 1", "Criterion 2"],
  "tests": ["pytest tests/"]
}
```

Slug: first 30 chars of lowercase title with non-alphanumeric replaced by hyphens

---

### `weld step snapshot --run <run_id> --n <int> [--iter <k>]`

Captures repo state for iteration `k` (default: 1).

Writes under `iter/<NN>/`:

* `diff.patch` - from `git diff` (unstaged changes)
* `checks/<category>.txt` - per-category check output
* `checks.summary.json` - aggregated check status

Rules:

* If diff is empty: writes status with `diff_nonempty=false` and exits (no review needed)

Exit codes:

* `0` success (including no-diff case)
* `3` not a git repo
* `1` step not selected

---

### `weld step review --run <run_id> --n <int> [--iter <k>]`

Runs configured provider review against step + diff + checks.

Writes:

* `iter/<NN>/review.md` - full review output
* `iter/<NN>/issues.json` - parsed issues
* `iter/<NN>/status.json` - derived status

Review output contract:

* Free-form markdown review
* **Last line** must be strict JSON:

```json
{"pass":true,"issues":[]}
```

Or with issues:

```json
{"pass":false,"issues":[{"severity":"blocker","file":"path","hint":"description","maps_to":"AC #1"}]}
```

Severity levels: `"blocker"`, `"major"`, `"minor"`

**Acceptance criteria enforcement:** Step passes only when ALL acceptance criteria are satisfied (no issues mapped to any criterion).

Status derivation:

* `pass` - true iff all acceptance criteria satisfied with no mapped issues
* `issue_count`, `blocker_count`, `major_count`, `minor_count` - counts by severity
* `checks_exit_code` - exit code from checks command
* `diff_nonempty` - true if diff had content

On parse failure:

* Stores error message as review content
* Sets `pass=false` with empty issues list

---

### `weld step fix-prompt --run <run_id> --n <int> --iter <k>`

Generates fix prompt for next iteration.

Writes:

* `prompt/fix.prompt.iter<k+1>.md`

Content structure:

* Issues grouped by severity (Blockers first, then Major, then Minor)
* For each issue: file + hint + mapping to acceptance criterion
* Original step body included
* Scope boundary: "Fix these issues only; no refactors or unrelated changes"

---

### `weld step loop --run <run_id> --n <int> [--max <m>] [--wait] [--manual] [--resume] [--all]`

Implements the main loop (Steps 3–5).

**`--resume` flag:** Continue from last iteration instead of starting fresh.

**`--all` flag:** Process all pending steps sequentially (see below).

Behavior:

1. Ensure step selected (auto-calls `step select` if needed)
2. Displays implementation prompt and configured models
3. For each iteration 1 to max_iterations (or from resume point):
   * In hybrid mode: invoke AI directly
   * In manual mode: skip AI, wait for user paste
   * With `--wait`: pause before AI invocation for prompt review
   * Capture diff via `capture_diff()`
   * If no diff: write status, continue to next iteration
   * Run checks via `run_checks()` (fail-fast)
   * Run all checks silently for review context
   * Run review via `run_step_review()`
   * Write results: `review.md`, `issues.json`, `status.json`
   * If pass: prompt for commit (see below)
   * Else: generate fix prompt, display/invoke it
4. Stop when pass or `max_iterations` reached

**Post-step commit prompt:**
After step passes, prompts: `'Commit changes now? [Y/n]'`
- Shows AI-generated commit message (semantic, no AI tool mentions)
- User can accept, decline, or edit (inline editing via prompt_toolkit)
- Commit message includes transcript trailer and Weld-Run trailer
- **Per-step enforcement:** Must commit before starting next step

**Timeout handling:** If AI invocation times out, partial output saved to `partial.md`, user prompted to continue from partial.

**Graceful quit:** Pressing 'q' during any interactive prompt saves current iteration state and exits cleanly for resume.

**`--all` mode behavior:**
1. Processes steps 1 through N sequentially
2. Skips steps marked as skipped
3. After each step passes, prompts for commit
4. If user declines commit, step is queued
5. At end of all steps, shows batch summary of queued commits:
   ```
   Pending commits:
   1. Step 1: <default message>
   2. Step 3: <default message>
   Commit all with default messages? [Y/n/individual]
   ```
6. If any step fails at max iterations, stops immediately (no skip-and-continue)

Writes per iteration:

* `iter/<NN>/diff.patch`
* `iter/<NN>/checks/<category>.txt`
* `iter/<NN>/checks.summary.json`
* `iter/<NN>/review.md`
* `iter/<NN>/issues.json`
* `iter/<NN>/status.json`
* `iter/<NN>/timing.json` (per-phase timing: AI, checks, review)
* `iter/<NN>/partial.md` (on timeout)
* `prompt/fix.iter<NN+1>.md` (if not passing and not at max)

Exit codes:

* `0` success
* `3` not a git repo
* `10` max iterations reached without passing

---

### `weld step amend --run <run_id> --n <int>`

Reopen a completed or skipped step for amendment.

**Behavior:**
1. For completed steps: Creates `iter-amend/` directory for new iteration series
2. For skipped steps: Un-skips and starts fresh implementation
3. Runs loop in appropriate directory
4. On completion, creates fixup commit (not git --amend)

Writes:
* `iter-amend/01/...`, `iter-amend/02/...`

Exit codes:
* `0` success
* `1` step not found
* `10` max iterations reached

---

## Transcript → Gist stage

### `weld transcript gist --run <run_id>`

Runs `claude-code-transcripts --gist` and extracts URLs.

**Per-run aggregate:** Generates one gist covering all step transcripts for the entire run.

Writes:

* `commit/transcript.json`:

```json
{
  "gist_url": "https://gist.github.com/...",
  "preview_url": "https://...",
  "raw_output": "...",
  "warnings": ["Could not auto-detect GitHub repo"]
}
```

Parsing:

* `Gist: <url>` pattern for gist_url
* `Preview: <url>` pattern for preview_url

Exit codes:

* `0` success with gist URL
* `3` not a git repo
* `21` failed to generate gist (no URL found)

---

## Commit stage

### `weld commit --run <run_id> -m "<message>" [--all] [--staged] [--interactive] [--strict]`

Default mode: `--staged` (only staged changes, default is True).

**Gist handling (warn and proceed):**
- If gist generation fails, commit proceeds without trailer
- Warning displayed: "Transcript gist failed, committing without provenance trailer"
- Use `--strict` to fail instead of warning

**`--interactive` flag:**
Selective file staging using checkbox UI (rich/prompt_toolkit):
```
Select files to commit:
[x] src/weld/cli.py
[ ] src/weld/config.py
[x] tests/test_cli.py
```

Behavior:

1. Stage changes if `--all` flag provided (`git add -A`)
2. If `--interactive`: show checkbox prompt for file selection
3. Verify staged changes exist (fail if none)
4. Attempt transcript gist generation (reuse if exists)
5. If gist fails: warn (or fail with `--strict`)
6. Build commit message with trailers (gist trailer omitted if failed)
7. Write `commit/message.txt`
8. Execute `git commit -F commit/message.txt`
9. Write `summary.md` with commit SHA and gist URL (if available)

Commit message format:

```
<subject from -m>

<commit_trailer_key>: <gist_url>  # omitted if gist failed
Weld-Run: .weld/runs/<run_id>
```

**Note:** Commit messages contain only semantic change information. No mentions of AI tools (Claude, Codex) in the message body - provenance is tracked via trailers only.

Exit codes:

* `0` committed
* `3` not a git repo
* `1` run not found
* `20` no staged changes
* `21` transcript generation failed (only with `--strict`)
* `22` git commit failed

---

### `weld list [--status <status>] [--since <date>] [--spec <pattern>] [--all]`

Lists all runs (implementation and discover) sorted newest first.

**Default behavior:** Shows only active runs (in-progress, completed). Abandoned runs are hidden.

**Filters:**
- `--status <status>`: Filter by status (in-progress, completed, abandoned)
- `--since <date>`: Filter runs created after date
- `--spec <pattern>`: Filter by spec filename pattern
- `--all`: Include abandoned runs

**Output format (combined view with type column):**
```
run_id                      | type     | status      | progress | age
20240115-103000-feature     | impl     | in-progress | step 3/5 | 2h ago
20240115-090000-discover    | discover | completed   | -        | 3h ago
20240114-090000-bugfix      | impl     | completed   | step 2/2 | 1d ago
```

Shows: run_id, type (impl/discover), status, progress, age.

Exit codes:

* `0` success
* `3` not a git repo

---

## Top-Level Command Aliases

Common commands are available as top-level aliases for convenience. Top-level commands take precedence over subcommands when names conflict.

| Alias | Equivalent |
|-------|------------|
| `weld init` | (already top-level) |
| `weld run` | (already top-level) |
| `weld status` | (already top-level) |
| `weld continue` | `weld run --continue` |
| `weld abandon` | `weld run abandon` |
| `weld commit` | (already top-level) |
| `weld next` | See below |

### `weld next`

Automatically select and start the next pending step.

**Behavior:**
1. Finds first step that is not completed and not skipped
2. Starts `weld step loop` for that step
3. If all steps complete: displays `'All steps complete! Run weld commit to finalize.'`

Exit codes:
* `0` success or all complete
* `1` no active run found
* `10` step failed at max iterations

---

## Run Selection Prompt

When a command requires `--run` but it's not provided:

1. If exactly one non-abandoned run exists: show interactive selection prompt
2. Prompt remembers last-used run as default
3. Shows rich context: run_id, age (e.g., '2h ago'), current stage, spec name

```
Select run [default: 20240115-103000-feature]:
  1. 20240115-103000-feature | step 3/5 | 2h ago
  2. 20240114-090000-bugfix  | plan     | 1d ago
>
```

---

## JSON Output Schema

All `--json` output includes a `schema_version` field for forward compatibility:

```json
{
  "schema_version": 1,
  "data": { ... }
}
```

**Schema versioning policy:**
- `schema_version` increments on breaking changes
- Output is always latest schema version (no version selection)
- Breaking changes only in major weld releases

---

## Custom Prompt Templates

Weld supports project-specific prompt customization.

### Setup

```bash
weld init --customize
# Creates .weld/templates/ with editable copies of all prompts
```

### Template Files

| Template | Purpose |
|----------|---------|
| `discover.prompt.md` | Generate architecture spec from codebase |
| `research.prompt.md` | Generate research from spec |
| `plan.prompt.md` | Generate plan from research |
| `plan.direct.prompt.md` | Generate plan directly from spec (skip-research) |
| `impl.prompt.md` | Implementation prompt for step |
| `fix.prompt.md` | Fix prompt template |
| `review.prompt.md` | Review prompt template |

### Template Variables

Templates use `{{variable}}` placeholders:
- `{{spec_content}}` - Spec file contents
- `{{research_content}}` - Research artifact contents
- `{{step_body}}` - Step markdown body
- `{{acceptance_criteria}}` - Formatted AC list
- `{{diff}}` - Git diff output
- `{{checks_output}}` - Check command output
- `{{issues}}` - Formatted issues list

---

## Service Adapters

### Codex Adapter (`services/codex.py`)

Invocation:

```python
run_codex(
    prompt: str,
    exec_path: str = "codex",
    sandbox: str = "read-only",
    model: str | None = None,
    cwd: Path | None = None,
    timeout: int | None = None,
) -> str
```

Command built: `[exec_path, "-p", prompt, "--sandbox", sandbox]`
With optional `["--model", model]` if model specified.

`parse_review_json()` - extracts JSON from last line of review output.

`extract_revised_plan()` - extracts content after `## Revised Plan` header.

### Claude Adapter (`services/claude.py`)

Invocation:

```python
run_claude(
    prompt: str,
    exec_path: str = "claude",
    model: str | None = None,
    cwd: Path | None = None,
    timeout: int | None = None,
) -> str
```

Command built: `[exec_path, "-p", prompt, "--output-format", "text"]`
With optional `["--model", model]` if model specified.

### Git Adapter (`services/git.py`)

All git operations use subprocess with timeout. Never uses `shell=True`.

Key functions:
- `get_repo_root()` - find repository root
- `get_current_branch()` - current branch name
- `get_head_sha()` - HEAD commit SHA
- `get_diff(staged: bool)` - diff output
- `has_staged_changes()` - check for staged changes
- `stage_all()` - `git add -A`
- `commit_file(message_file)` - `git commit -F`

### Checks Adapter (`services/checks.py`)

```python
run_checks(
    checks_config: dict[str, str],
    order: list[str],
    cwd: Path,
    timeout: int | None = None,
    fail_fast: bool = True,
) -> ChecksResult
```

* Commands parsed via `shlex.split()` - **no shell=True**
* Returns `ChecksResult` with per-category status and output
* `fail_fast=True` for iteration, `fail_fast=False` for review input

---

## Data models (Pydantic)

### `Meta` (`models/meta.py`)

```python
class Meta(BaseModel):
    run_id: str
    created_at: datetime
    updated_at: datetime
    repo_root: Path
    branch: str
    head_sha: str
    config_hash: str
    tool_versions: dict[str, str] = {}
    plan_parse_warnings: list[str] = []
    research_version: int = 1
    plan_version: int = 1
    stale_artifacts: list[str] = []  # ["plan", "step-01"]
    stale_overrides: list[StaleOverride] = []  # Audit log of forced-stale decisions
    abandoned: bool = False
    abandoned_at: datetime | None = None
    last_used_at: datetime | None = None  # For run selection default
    command_history: list[CommandEvent] = []  # Commands executed

class StaleOverride(BaseModel):
    timestamp: datetime
    artifact: str
    stale_reason: str

class CommandEvent(BaseModel):
    timestamp: datetime
    command: str
```

### `SpecRef` (`models/meta.py`)

```python
class SpecRef(BaseModel):
    absolute_path: Path
    sha256: str
    size_bytes: int
    git_blob_id: str | None = None
    source_discover_id: str | None = None  # If spec came from discover
```

### `Step` (`models/step.py`)

```python
class Step(BaseModel):
    n: int
    title: str
    slug: str
    body_md: str
    acceptance_criteria: list[str] = []
    tests: list[str] = []
    skipped: bool = False
    skip_reason: str | None = None
```

### `Issue` (`models/issues.py`)

```python
class Issue(BaseModel):
    severity: Literal["blocker", "major", "minor"]
    file: str
    hint: str
    maps_to: str | None = None
```

### `Issues` (`models/issues.py`)

```python
class Issues(BaseModel):
    pass_: bool = Field(alias="pass")
    issues: list[Issue] = []
```

### `Status` (`models/status.py`)

```python
class Status(BaseModel):
    pass_: bool = Field(alias="pass")
    issue_count: int = 0
    blocker_count: int = 0
    major_count: int = 0
    minor_count: int = 0
    checks_summary: ChecksSummary
    diff_nonempty: bool
    timestamp: datetime
```

### `Lock` (`models/lock.py`)

```python
class Lock(BaseModel):
    pid: int
    run_id: str
    command: str
    started_at: datetime
    last_heartbeat: datetime
```

### `VersionInfo` (`models/version_info.py`)

```python
class VersionInfo(BaseModel):
    version: int
    created_at: datetime
    review_id: str | None = None
    trigger_reason: str | None = None
    superseded_at: datetime | None = None
```

### `DiscoverMeta` (`models/discover.py`)

```python
class DiscoverMeta(BaseModel):
    discover_id: str
    created_at: datetime
    config_hash: str
    output_path: Path                # User-specified output location
    used_by_runs: list[str] = []     # Implementation run IDs using this discover
    partial: bool = False            # True if analysis was interrupted
```

### `ChecksSummary` (`models/status.py`)

```python
class CategoryResult(BaseModel):
    exit_code: int
    passed: bool

class ChecksSummary(BaseModel):
    categories: dict[str, CategoryResult]
    first_failure: str | None = None
    all_passed: bool
```

### `Timing` (`models/timing.py`)

```python
class Timing(BaseModel):
    ai_invocation_ms: int
    checks_ms: int
    review_ms: int
    total_ms: int
```

---

## Architecture Notes

### Layered Design

1. **CLI Layer** (`cli.py`, `commands/`) - Typer entry points, argument parsing, output formatting
2. **Core Layer** (`core/`) - Business logic, no external I/O
3. **Services Layer** (`services/`) - External tool integrations (git, codex, claude, transcripts)
4. **Models Layer** (`models/`) - Pydantic data structures

### Command → Core → Services Pattern

Commands delegate to core functions:
- `commands/step.py::step_loop` → `core/loop.py::run_step_loop`
- `commands/research.py::research_review` → `core/review_engine.py::run_review`
- `commands/plan.py::plan_review` → `core/review_engine.py::run_review`

### Review Engine Multi-Provider Support

`core/review_engine.py` routes to appropriate provider:
- Reads task config for the specified task type
- Calls appropriate provider based on config (codex, claude, or custom)
- Uses unified `parse_*_review()` for JSON extraction
- Enforces strict JSON-only format (no YAML or heuristic parsing)

### New Core Modules

- `core/lock_manager.py` - PID-based run locking
- `core/artifact_versioning.py` - Version history and lineage tracking

---

## Debug Logging

Opt-in persistent debug logging for troubleshooting.

### Enable

Config:
```toml
[debug]
log = true
```

Or per-invocation:
```bash
weld --debug step loop --run <id> --n 1
```

### Log Contents

`.weld/debug.log`:
- All subprocess commands with arguments
- Timing information (command duration)
- Internal state transitions
- Error details and stack traces
- AI invocation requests and responses (truncated)

### Log Rotation

Debug log rotates at 10MB, keeping last 3 files:
- `debug.log` (current)
- `debug.log.1`
- `debug.log.2`

---

## Interactive Keyboard Shortcuts

Standard keyboard shortcuts available during interactive prompts:

| Key | Action |
|-----|--------|
| `y` | Confirm / Yes |
| `n` | Decline / No |
| `q` | Quit (graceful, saves state) |
| `h` | Show contextual help for current prompt |
| `?` | Show available options |
| Enter | Accept default option |

**Graceful quit behavior:** When 'q' is pressed during an interactive prompt in a loop, weld saves the current iteration state and exits cleanly. The run can be resumed with `--resume`.

**Contextual help:** Pressing 'h' shows help specific to the current prompt (not general weld help).

---

## Per-Phase Timing

Weld tracks timing information per-phase for each iteration, enabling workflow optimization.

### Phases Tracked

- **AI invocation**: Time from request to response
- **Checks**: Time running lint/typecheck/test
- **Review**: Time for AI review invocation

### Real-Time Display

During long-running operations, elapsed time is shown with animated spinner:
```
⠋ Waiting for AI (45s)...
```

### Stored Timing Data

`iter/<NN>/timing.json`:
```json
{
  "ai_invocation_ms": 45230,
  "checks_ms": 12450,
  "review_ms": 23100,
  "total_ms": 80780
}
```

---

## Dry-Run Mode

All commands support `--dry-run` to preview effects without applying.

**Preview detail:** Shows first 10 lines of content that would be written, then `'... (N more lines)'`.

Example:
```
$ weld step loop --run <id> --n 1 --dry-run

Would write: .weld/runs/<id>/steps/01-feature/prompt/impl.prompt.md
--- Content preview (first 10 lines) ---
# Implementation Prompt for Step 1
...
--- (42 more lines) ---

Would invoke: claude -p "..." --output-format text
Would write: .weld/runs/<id>/steps/01-feature/iter/01/status.json
```

---

## Error Messages

Error messages include suggested next actions for user guidance.

**Format:**
```
Error: <description>
  Run: <suggested command>
```

**Examples:**
```
Error: No research artifact found
  Run: weld research import --run <id> --file <path>

Error: Plan derived from stale research
  Run: weld plan prompt --run <id> (to regenerate)
```

---

## UX behavior

* **Hybrid AI invocation**: Direct provider calls by default, `--manual` for clipboard workflow
* **Interactive prompts**: Rate limits and parse failures prompt user for action
* **Artifact-driven**: each stage produces an MD file that feeds the next stage
* **Independent stages**: each command can be run independently with an imported artifact
* **Everything inspectable**: all artifacts stored under `.weld/runs/...`
* **Model info displayed**: provider and model name shown at each stage
* **Review is optional**: user decides when to invoke review on any artifact
* **Global dry-run**: any command supports `--dry-run` to preview effects (10-line content preview)
* **Progress feedback**: Long-running operations show animated spinner with elapsed time
* **Per-step commits**: Commits enforced after each step; cannot start next step without committing
* **Graceful quit**: 'q' key saves state and exits cleanly for resume
* **Rich run selection**: Interactive prompts show run context (age, stage, spec name)
* **AI-generated commit messages**: Semantic messages without AI tool mentions; trailers for provenance

---

## Definition of done

### Greenfield E2E Flow

```bash
uv venv
uv pip install -e .

weld init
# User creates spec.md externally
weld run --spec specs/horizon.md

# Stage 1: Research (AI invoked automatically in hybrid mode)
# Or use --manual to copy/paste
weld research import --run <run_id> --file research.md  # if manual
# Optional: review research (prompts for revision)
weld research review --run <run_id>

# Stage 2: Plan
weld plan prompt --run <run_id>
weld plan import --run <run_id> --file plan.md  # if manual
# Optional: review plan (prompts for revision)
weld plan review --run <run_id>

# Stage 3: Implement (prompts for commit after each step)
weld step loop --run <run_id> --n 1
# Or process all steps:
weld step loop --run <run_id> --all
# Or use shortcut:
weld next
```

### Brownfield E2E Flow

```bash
weld init

# Step 1: Discover existing codebase architecture
weld discover --output docs/architecture.md
# Prompts: "Refine this spec? [y/n]"
# If yes, launches interview

# Step 2: Optionally refine architecture spec
weld interview docs/architecture.md --focus 'data flow'

# Step 3: Create feature spec (user writes this, referencing architecture)
# specs/new-feature.md

# Step 4: Run implementation workflow
weld run --spec specs/new-feature.md

# Continue with research → plan → implement as in greenfield
weld research review --run <run_id>
weld plan prompt --run <run_id>
weld step loop --run <run_id> --all
```

### Skip-research flow:

```bash
weld run --spec specs/simple-feature.md --skip-research
weld plan import --run <run_id> --file plan.md
weld step loop --run <run_id> --n 1
```

Resume and amend flows:

```bash
# Resume interrupted loop
weld step loop --run <run_id> --n 1 --resume

# Amend completed step
weld step amend --run <run_id> --n 1

# Skip a step
weld step skip --run <run_id> --n 2 --reason "Already implemented"
```

Top-level shortcuts:

```bash
weld continue      # Resume incomplete run
weld abandon       # Abandon a run
weld next          # Start next pending step
```

Diagnostics:

```bash
weld doctor        # Comprehensive health check (offers safe fixes)
weld status        # Dashboard of current run
weld config validate  # Validate configuration
weld run history --run <id>  # View command history
weld run report --run <id>   # Generate summary report
```

Result:

* `.weld/runs/<run_id>/` contains all artifacts with version history
* Each artifact is an inspectable MD file
* Commit message contains semantic description + `Claude-Transcript: <gist-url>` trailer
* Per-phase timing tracked in `timing.json` per iteration
* Iteration loop stops only when ALL acceptance criteria are satisfied
* Interrupted runs can be resumed with graceful quit support
* Completed or skipped steps can be amended
* Interactive prompts with standard shortcuts (y/n/q/h/?)
