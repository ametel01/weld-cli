# Research: SPECS.md Gap Analysis - Current Implementation vs Specification

## Executive Summary

The weld-cli codebase has a **partial implementation** of the specification. The current implementation covers the core workflow loop (run → plan → implement → review → commit) but lacks many features defined in SPECS.md. The codebase follows a clean layered architecture (CLI → commands → core → services → models) that makes extension straightforward.

**Implementation completeness by area:**
- Core loop (plan → step → review → commit): ~85% complete
- Configuration system: ~70% complete
- CLI commands: ~40% of specified commands exist
- Research/Discover/Interview phases: 0% complete
- Artifact versioning/lineage: 0% complete
- Interactive UX features: ~20% complete

**Critical gaps requiring implementation:**
1. **Research phase** - Spec describes research as first phase before planning; codebase skips directly to plan generation
2. **Discover workflow** - Brownfield project support is completely missing
3. **Interview system** - No interactive Q&A refinement exists
4. **Artifact versioning** - No history tracking or lineage management
5. **Run locking** - No concurrent run prevention
6. **Multi-category checks** - Single command vs spec's category-based checks with fail-fast
7. **Many CLI commands** - Missing: discover, interview, status, doctor, config validate, run continue/abandon/report/history, research commands, step skip/amend, weld next

**What exists and works:**
- Run creation with spec reference
- Plan parsing (strict/lenient formats)
- Step selection and implementation prompts
- Review engine with multi-provider support
- Implement-review-fix loop
- Transcript gist generation and commit handling
- Configuration system with per-task model routing

---

## Authoritative Files

### Core Implementation
| File | Purpose | Key Exports | Lines |
|------|---------|-------------|-------|
| `src/weld/cli.py` | CLI entry point, Typer setup | `app`, `get_output_context()` | 1-137 |
| `src/weld/config.py` | Configuration management | `WeldConfig`, `TaskType`, `load_config()` | 1-181 |
| `src/weld/core/run_manager.py` | Run lifecycle utilities | `create_run_directory()`, `create_meta()`, `generate_run_id()` | 1-181 |
| `src/weld/core/plan_parser.py` | Plan parsing | `parse_steps()`, `generate_plan_prompt()` | 1-259 |
| `src/weld/core/step_processor.py` | Step management | `create_step_directory()`, `generate_impl_prompt()`, `generate_fix_prompt()` | 1-226 |
| `src/weld/core/review_engine.py` | Review orchestration | `run_step_review()` | 1-100 |
| `src/weld/core/loop.py` | Main iteration loop | `run_step_loop()`, `LoopResult` | 1-154 |
| `src/weld/core/commit_handler.py` | Commit handling | `do_commit()`, `ensure_transcript_gist()` | 1-154 |

### Services Layer
| File | Purpose | Key Functions | Lines |
|------|---------|---------------|-------|
| `src/weld/services/git.py` | Git operations | `get_repo_root()`, `get_diff()`, `commit_file()` | 1-165 |
| `src/weld/services/codex.py` | Codex CLI integration | `run_codex()`, `parse_review_json()` | 1-128 |
| `src/weld/services/claude.py` | Claude CLI integration | `run_claude()`, `parse_review_json()` | 1-90 |
| `src/weld/services/checks.py` | Checks runner | `run_checks()` | 1-72 |
| `src/weld/services/transcripts.py` | Transcript gist | `run_transcript_gist()` | 1-85 |
| `src/weld/services/diff.py` | Diff capture | `capture_diff()`, `write_diff()` | 1-55 |
| `src/weld/services/filesystem.py` | File I/O utilities | `ensure_directory()`, `write_file()` | 1-75 |

### Models
| File | Purpose | Key Models | Lines |
|------|---------|------------|-------|
| `src/weld/models/meta.py` | Run metadata | `Meta`, `SpecRef` | 1-64 |
| `src/weld/models/step.py` | Parsed steps | `Step` | 1-44 |
| `src/weld/models/issues.py` | Review issues | `Issue`, `Issues` | 1-55 |
| `src/weld/models/status.py` | Iteration status | `Status` | 1-44 |

### Test Files (for pattern reference)
| File | What it Tests | Useful Patterns | Lines |
|------|---------------|-----------------|-------|
| `tests/conftest.py` | Shared fixtures | `temp_git_repo`, `initialized_weld`, `run_with_plan` | 1-162 |
| `tests/test_integration.py` | Full workflows | CLI invocation patterns, directory structure verification | 1-795 |
| `tests/test_cli.py` | CLI commands | Global option handling, error scenarios | 1-302 |

---

## Gap Analysis by Feature Area

### 1. Research Phase (COMPLETELY MISSING)

**Spec requirement (SPECS.md lines 96-117):**
- Research is the first phase after `weld run --spec`
- Generates research artifact from spec
- Research can be reviewed and revised
- Research has version history

**Current state:**
- `weld run --spec` generates plan prompt directly (`core/plan_parser.py:9-56`)
- No `research/` subdirectory in run structure
- No research commands exist

**Current directory structure created (`core/run_manager.py:80-98`):**
```python
def create_run_directory(weld_dir: Path, run_id: str) -> Path:
    run_dir = weld_dir / "runs" / run_id
    (run_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (run_dir / "plan").mkdir(parents=True, exist_ok=True)
    (run_dir / "steps").mkdir(parents=True, exist_ok=True)
    (run_dir / "commit").mkdir(parents=True, exist_ok=True)
    return run_dir
```
**Missing:** `research/` directory

**Files to create:**
```
src/weld/commands/research.py
src/weld/core/research_processor.py
```

**Files to modify:**
- `src/weld/core/run_manager.py:92` - add `(run_dir / "research").mkdir()`
- `src/weld/commands/run.py:59-67` - generate research prompt instead of plan prompt
- `src/weld/cli.py:44-50` - add `research_app` typer group
- `src/weld/commands/__init__.py` - export research commands

**Pattern to follow:** See `commands/plan.py:16-61` for import/review pattern

---

### 2. Discover Workflow (COMPLETELY MISSING)

**Spec requirement (SPECS.md lines 222-268, 979-1015):**
- `weld discover --output <path>` analyzes codebase
- Generates architecture spec with file:line references (no code snippets)
- Stored in `.weld/discover/<discover_id>/`
- Bi-directional lineage tracking with implementation runs
- Auto-prune to keep last 3 versions
- Post-generation prompts for interview refinement

**Current state:** Nothing exists.

**Files to create:**
```
src/weld/commands/discover.py
src/weld/core/discover_engine.py
src/weld/models/discover.py
```

**Model to add (from SPECS.md lines 1965-1973):**
```python
class DiscoverMeta(BaseModel):
    discover_id: str
    created_at: datetime
    config_hash: str
    output_path: Path
    used_by_runs: list[str] = []
    partial: bool = False
```

**Extension point in `SpecRef` model (`models/meta.py:13-30`):**
```python
# Add to SpecRef:
source_discover_id: str | None = None  # If spec came from discover
```

---

### 3. Interview System (COMPLETELY MISSING)

**Spec requirement (SPECS.md lines 1017-1043):**
- `weld interview <file> [--focus <topic>]`
- Interactive Q&A to refine any markdown document
- Questions one at a time, AI adapts based on answers
- Contradiction detection with immediate pause for clarification
- Questions focus on requirements (what), not implementation (how)
- Updates file in-place (no backup; user has git)
- Each session starts fresh (no memory of previous sessions)

**Current state:** Nothing exists.

**Files to create:**
```
src/weld/commands/interview.py
src/weld/core/interview_engine.py
```

---

### 4. Artifact Versioning (COMPLETELY MISSING)

**Spec requirement (SPECS.md lines 643-695):**
- Research and plan have `history/v<n>/` subdirectories
- Each version has `content.md` and `meta.json`
- Lineage tracking: plan tracks which research version it came from
- Stale artifact detection and warnings with user confirmation

**Current state:**
- `plan_import` overwrites files without history (`commands/plan.py:16-61`)
- Current naming: `plan.raw.md`, `plan.final.md` (not spec's `plan.md`)
- No version tracking in `Meta` model

**Current Meta model (`models/meta.py:33-63`):**
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
    # MISSING: research_version, plan_version, stale_artifacts, stale_overrides, command_history
```

**Model additions needed (from SPECS.md lines 1853-1882):**
```python
# Add to Meta model:
research_version: int = 1
plan_version: int = 1
stale_artifacts: list[str] = []
stale_overrides: list[StaleOverride] = []
last_used_at: datetime | None = None
command_history: list[CommandEvent] = []
abandoned: bool = False
abandoned_at: datetime | None = None

class StaleOverride(BaseModel):
    timestamp: datetime
    artifact: str
    stale_reason: str

class CommandEvent(BaseModel):
    timestamp: datetime
    command: str
```

**Files to create:**
```
src/weld/core/artifact_versioning.py
src/weld/models/version_info.py
```

**VersionInfo model (from SPECS.md lines 1952-1960):**
```python
class VersionInfo(BaseModel):
    version: int
    created_at: datetime
    review_id: str | None = None
    trigger_reason: str | None = None
    superseded_at: datetime | None = None
```

---

### 5. Run Locking (COMPLETELY MISSING)

**Spec requirement (SPECS.md lines 727-759):**
- `.weld/active.lock` prevents concurrent runs
- PID-based stale lock detection
- Lock required for run-modifying commands
- Lock NOT required for read-only commands (status, list, doctor)

**Current state:** No locking mechanism exists.

**Files to create:**
```
src/weld/core/lock_manager.py
src/weld/models/lock.py
```

**Model from SPECS.md (lines 1943-1950):**
```python
class Lock(BaseModel):
    pid: int
    run_id: str
    command: str
    started_at: datetime
    last_heartbeat: datetime
```

**Commands requiring lock (SPECS.md lines 750-759):**
- `weld run` (creating new run)
- `weld research import`, `weld plan import`
- `weld step loop`, `weld step amend`
- `weld commit`

---

### 6. Multi-Category Checks (PARTIAL - needs restructure)

**Spec requirement (SPECS.md lines 592-639):**
```toml
[checks]
lint = "ruff check ."
test = "pytest tests/"
typecheck = "pyright"
order = ["lint", "typecheck", "test"]
```
- Fail-fast during iteration (stop at first failure)
- Run all checks for review context (even after fail-fast)
- Per-category output files: `checks/<category>.txt`
- Aggregated `checks.summary.json`

**Current state (`config.py:45-48`):**
```python
class ChecksConfig(BaseModel):
    command: str = "echo 'No checks configured'"
```
Single command only, no categories.

**Current check execution (`services/checks.py:16-60`):**
```python
def run_checks(
    command: str,
    cwd: Path,
    timeout: int | None = None,
) -> tuple[str, int]:
```
Returns single output, single exit code.

**Current loop usage (`core/loop.py:113`):**
```python
checks_output, checks_exit = run_checks(config.checks.command, repo_root)
write_checks(iter_dir / "checks.txt", checks_output)
```
Writes to single `checks.txt` file.

**Files to modify:**
- `src/weld/config.py:45-48` - restructure ChecksConfig
- `src/weld/services/checks.py:16-60` - add multi-category support
- `src/weld/core/loop.py:113` - use fail-fast logic
- `src/weld/models/status.py` - add ChecksSummary

**Model to add (from SPECS.md lines 1976-1987):**
```python
class CategoryResult(BaseModel):
    exit_code: int
    passed: bool

class ChecksSummary(BaseModel):
    categories: dict[str, CategoryResult]
    first_failure: str | None = None
    all_passed: bool
```

**Current Status model (`models/status.py:1-44`):**
```python
class Status(BaseModel):
    pass_: bool = Field(alias="pass")
    issue_count: int = 0
    blocker_count: int = 0
    major_count: int = 0
    minor_count: int = 0
    checks_exit_code: int = 0  # CHANGE: Replace with checks_summary: ChecksSummary
    diff_nonempty: bool = True
    timestamp: datetime = Field(default_factory=datetime.now)
```

---

### 7. Skip-Research Mode (PARTIALLY EXISTS - needs flag)

**Spec requirement (SPECS.md lines 699-722):**
- `weld run --spec <path> --skip-research` generates plan directly
- Uses `plan.direct.prompt.md` template
- Creates run without `research/` subdirectory

**Current state:** Current behavior IS skip-research (no research phase), but:
- No `--skip-research` flag exists
- No dedicated `plan.direct.prompt.md` template
- Should become opt-in once research phase is implemented

**Files to modify:**
- `src/weld/commands/run.py:23-26` - add `--skip-research` flag
- `src/weld/core/run_manager.py:80-98` - conditional directory creation

---

### 8. TaskType Enum Incomplete

**Spec requirement (SPECS.md lines 568-579):**
```
discover, interview, research, research_review, plan, plan_review,
implementation, implementation_review, fix
```

**Current state (`config.py:11-18`):**
```python
class TaskType(str, Enum):
    PLAN_GENERATION = "plan_generation"
    PLAN_REVIEW = "plan_review"
    IMPLEMENTATION = "implementation"
    IMPLEMENTATION_REVIEW = "implementation_review"
    FIX_GENERATION = "fix_generation"
```

**Missing task types:** `DISCOVER`, `INTERVIEW`, `RESEARCH`, `RESEARCH_REVIEW`

**Note:** Spec uses `plan` and `fix` but implementation uses `plan_generation` and `fix_generation`. Need to decide on naming convention.

---

### 9. CLI Commands Missing

#### Currently Implemented Commands:
| Command | Status | Location | Notes |
|---------|--------|----------|-------|
| `weld init` | ✅ Complete | `commands/init.py:12-90` | |
| `weld run --spec` | ⚠️ Partial | `commands/run.py:12-72` | Missing --skip-research, --continue, --name |
| `weld plan import` | ✅ Complete | `commands/plan.py:16-61` | |
| `weld plan review` | ✅ Complete | `commands/plan.py:64-123` | |
| `weld step select` | ✅ Complete | `commands/step.py:26-82` | |
| `weld step snapshot` | ✅ Complete | `commands/step.py:84-137` | |
| `weld step review` | ✅ Complete | `commands/step.py:139-200` | |
| `weld step fix-prompt` | ✅ Complete | `commands/step.py:202-245` | |
| `weld step loop` | ⚠️ Partial | `commands/step.py:248-326` | Missing --resume, --all, --manual |
| `weld commit` | ⚠️ Partial | `commands/commit.py:16-89` | Missing --interactive, --strict |
| `weld list` | ⚠️ Basic | `commands/commit.py:92-118` | Missing filters (--status, --since, --spec, --all) |
| `weld transcript gist` | ✅ Complete | `commands/commit.py:121-155` | |

#### Missing Commands:
| Command | Spec Reference | Priority | Complexity |
|---------|----------------|----------|------------|
| `weld discover` | Lines 979-1015 | High | High |
| `weld interview` | Lines 1017-1043 | High | High |
| `weld status` | Lines 1045-1066 | Medium | Low |
| `weld doctor` | Lines 942-976 | Medium | Medium |
| `weld config validate` | Lines 1069-1089 | Low | Low |
| `weld run --continue` | Lines 1118-1129 | Medium | Medium |
| `weld run abandon` | Lines 1131-1141 | Low | Low |
| `weld run report` | Lines 1143-1159 | Low | Low |
| `weld run history` | Lines 1161-1182 | Low | Low |
| `weld research import` | Lines 1186-1200 | High | Low |
| `weld research review` | Lines 1202-1226 | High | Medium |
| `weld research prompt` | Lines 1228-1237 | Medium | Low |
| `weld plan prompt` | Lines 1241-1265 | Medium | Low |
| `weld step skip` | Lines 1315-1330 | Medium | Low |
| `weld step amend` | Lines 1540-1558 | Medium | Medium |
| `weld next` | Lines 1689-1700 | Medium | Low |

---

### 10. Global CLI Options Missing

**Spec requirement (SPECS.md lines 897-909):**
```
--dry-run    # Preview effects without applying
--debug      # Enable debug logging for this invocation
```

**Current state (`cli.py:66-97`):**
```python
@app.callback()
def main(
    version: bool = ...,
    verbose: int = ...,
    quiet: bool = ...,
    json_output: bool = ...,
    no_color: bool = ...,
) -> None:
```
Has: `--version`, `--verbose`, `--quiet`, `--json`, `--no-color`
Missing: `--dry-run`, `--debug`

---

### 11. Directory Structure Differences

**Spec structure (SPECS.md lines 306-376) vs Current implementation:**

```
.weld/
  config.toml                 # ✅ EXISTS
  active.lock                 # ❌ MISSING (run locking)
  debug.log                   # ❌ MISSING (debug logging)
  discover/                   # ❌ MISSING (discover workflow)
  templates/                  # ❌ MISSING (custom templates)
  runs/
    <run_id>/
      meta.json               # ✅ EXISTS
      inputs/
        spec.ref.json         # ✅ EXISTS
      research/               # ❌ MISSING (research phase)
        prompt.md
        research.md
        history/              # ❌ MISSING (artifact versioning)
        review.prompt.md
        review.md
      plan/
        prompt.md             # ✅ EXISTS
        plan.md               # ⚠️ DIFFERENT: uses plan.raw.md, plan.final.md
        history/              # ❌ MISSING (artifact versioning)
        review.prompt.md      # ✅ EXISTS (different naming)
        review.md             # ✅ EXISTS (different naming)
      steps/
        01-<slug>/
          step.json           # ✅ EXISTS
          prompt/
            impl.prompt.md    # ✅ EXISTS
            fix.iter<NN>.md   # ⚠️ DIFFERENT: fix.prompt.iter<NN>.md
          iter/
            01/
              diff.patch      # ✅ EXISTS
              checks/         # ❌ MISSING: uses checks.txt (single file)
                lint.txt
                test.txt
                typecheck.txt
              checks.summary.json  # ❌ MISSING
              review.md       # ✅ EXISTS (as codex.review.md)
              issues.json     # ✅ EXISTS (as codex.issues.json)
              status.json     # ✅ EXISTS
              timing.json     # ❌ MISSING (per-phase timing)
              partial.md      # ❌ MISSING (timeout handling)
            iter-amend/       # ❌ MISSING (step amend)
      commit/
        transcript.json       # ✅ EXISTS
        message.txt           # ✅ EXISTS
      summary.md              # ❌ MISSING
```

---

### 12. Custom Prompt Templates (MISSING)

**Spec requirement (SPECS.md lines 1742-1776):**
- `weld init --customize` copies templates to `.weld/templates/`
- `weld init --reset-templates` restores defaults
- Templates use `{{variable}}` placeholders
- Templates: `discover.prompt.md`, `research.prompt.md`, `plan.prompt.md`, `plan.direct.prompt.md`, `impl.prompt.md`, `fix.prompt.md`, `review.prompt.md`

**Current state:** Templates are hardcoded in:
- `core/plan_parser.py:9-56` - plan prompt
- `core/step_processor.py:66-108` - impl prompt
- `core/step_processor.py:111-165` - fix prompt
- `core/step_processor.py:168-225` - review prompt

**Current init command (`commands/init.py`):**
```python
def init(...) -> None:
```
No `--customize` or `--reset-templates` flags.

---

### 13. .weldignore Support (MISSING)

**Spec requirement (SPECS.md lines 262-301):**
- `.weldignore` in repo root
- Gitignore-style patterns
- Language-specific defaults detected during `weld init`
- Applied to discover, research, and plan generation

**Current state:** Nothing exists.

**Files to create:**
```
src/weld/core/ignore_patterns.py
```

---

### 14. Debug Logging (MISSING)

**Spec requirement (SPECS.md lines 2032-2060):**
- `[debug] log = true` in config
- `--debug` CLI flag for per-invocation
- Log rotation at 10MB, keeping last 3 files
- Logs: subprocess commands, timing, state transitions, errors, AI requests/responses (truncated)

**Current state (`logging.py`):**
- Basic Rich logging setup
- No persistent file logging
- No debug mode

---

### 15. Per-Phase Timing (MISSING)

**Spec requirement (SPECS.md lines 2085-2110):**
- Track timing per iteration: AI invocation, checks, review
- Write to `iter/<NN>/timing.json`
- Real-time display with animated spinner

**Current state:** No timing tracked.

**Model from SPECS.md (lines 1989-1996):**
```python
class Timing(BaseModel):
    ai_invocation_ms: int
    checks_ms: int
    review_ms: int
    total_ms: int
```

---

### 16. Interactive Features (PARTIAL)

**Spec requirement (SPECS.md lines 2062-2083):**
- Keyboard shortcuts: y/n/q/h/?
- Graceful quit saves state for resume
- Contextual help ('h' shows current prompt help)

**Spec requirement (SPECS.md lines 1601-1613):**
- `--interactive` flag for commit with checkbox file selection

**Current state:**
- Basic `input()` wait in loop (`core/loop.py:91-92`)
- No graceful quit handling
- No keyboard shortcuts
- No checkbox UI for file selection

---

### 17. JSON Output Schema Versioning (MISSING)

**Spec requirement (SPECS.md lines 1724-1740):**
```json
{
  "schema_version": 1,
  "data": { ... }
}
```

**Current state (`output.py:22-25`):**
```python
def print_json(self, data: dict[str, Any]) -> None:
    if self.json_mode:
        print(json.dumps(data, indent=2, default=str))
```
No `schema_version` wrapper.

---

### 18. Error Message Format (PARTIAL)

**Spec requirement (SPECS.md lines 2138-2155):**
```
Error: <description>
  Run: <suggested command>
```

**Current state (`output.py:34-39`):**
```python
def error(self, message: str, data: dict[str, Any] | None = None) -> None:
    if self.json_mode and data:
        self.print_json({"error": message, **data})
    else:
        self.console.print(f"[red]Error: {message}[/red]")
```
Errors use Rich formatting but no suggested next action.

---

### 19. Invoke Mode Options (PARTIAL)

**Spec requirement (SPECS.md lines 761-817):**
- Hybrid mode (default): AI invoked automatically
- Manual mode (`--manual` flag): User pastes output
- Wait mode (`--wait` flag): Pause before AI invocation

**Current state:**
- `--wait` implemented in `step_loop` (`commands/step.py:252`)
- `--manual` flag NOT implemented
- No `[invoke] mode = "manual"` config support

**Current config (`config.py:94-127`):**
No `invoke` section defined.

---

### 20. Run Selection Prompt (MISSING)

**Spec requirement (SPECS.md lines 1706-1720):**
When `--run` not provided:
- If exactly one non-abandoned run exists: show interactive selection
- Remember last-used run as default
- Show rich context (age, stage, spec name)

**Current state:** Commands fail if `--run` not provided.

---

## Implementation Patterns

### Pattern: Command Implementation
**Used in:** All files in `commands/`

```python
# commands/plan.py:16-61
def plan_import(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    file: Path = typer.Option(..., "--file", "-f", help="Plan file from Claude"),
) -> None:
    """Import Claude's plan output."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    # ... delegate to core
```

**When to apply:** All new CLI commands should follow this structure.

### Pattern: Service Integration
**Used in:** `services/codex.py`, `services/claude.py`

```python
# services/codex.py:17-60
def run_codex(
    prompt: str,
    exec_path: str = "codex",
    sandbox: str = "read-only",
    model: str | None = None,
    cwd: Path | None = None,
    timeout: int | None = None,
) -> str:
    timeout = timeout or CODEX_TIMEOUT
    cmd = [exec_path, "-p", prompt, "--sandbox", sandbox]
    if model:
        cmd.extend(["--model", model])
    # subprocess.run without shell=True
```

**When to apply:** All external CLI integrations.

### Pattern: Core Function Structure
**Used in:** All files in `core/`

```python
# core/review_engine.py:23-99
def run_step_review(
    step: Step,
    diff: str,
    checks_output: str,
    checks_exit_code: int,
    config: WeldConfig,
    cwd: Path,
) -> tuple[str, Issues, Status]:
    """Run review using configured provider and return (review_md, issues, status)."""
    # Pure business logic, delegates to services for I/O
```

**When to apply:** All business logic functions.

---

## Dependencies & Constraints

### External Dependencies
| Tool | Validation Point | Purpose |
|------|------------------|---------|
| `git` | `commands/init.py:47` | Version control |
| `gh` | `commands/init.py:47` | GitHub CLI |
| `codex` | `commands/init.py:47` | OpenAI Codex CLI |
| `claude-code-transcripts` | `commands/init.py:47` | Transcript generation |
| `claude` | `services/claude.py:17` | Claude CLI (optional) |

### Timeout Constants (`constants.py:14-35`)
| Constant | Value | Purpose |
|----------|-------|---------|
| `GIT_TIMEOUT` | 30s | Git commands |
| `CODEX_TIMEOUT` | 600s | Codex invocations |
| `CLAUDE_TIMEOUT` | 600s | Claude invocations |
| `TRANSCRIPT_TIMEOUT` | 60s | Gist generation |
| `CHECKS_TIMEOUT` | 300s | Running checks |
| `INIT_TOOL_CHECK_TIMEOUT` | 10s | Tool availability |

### Invariants
- All subprocess calls use `subprocess.run()` without `shell=True` (security)
- All file paths are validated within repo bounds (`validation.py`)
- Run IDs follow `YYYYMMDD-HHMMSS-slug` format (`core/run_manager.py:13-33`)
- Config is read-only during command execution

---

## Extension Points

### Where to Add New Commands
| Location | Type of Change | Pattern to Follow |
|----------|---------------|-------------------|
| `src/weld/commands/` | New command file | See `commands/plan.py` |
| `src/weld/cli.py:110-132` | Register command | `app.command()(function_name)` |
| `src/weld/commands/__init__.py` | Export | Add to `__all__` |

### Where to Add New Models
| Location | Type of Change | Pattern to Follow |
|----------|---------------|-------------------|
| `src/weld/models/` | New model file | See `models/step.py` |
| `src/weld/models/__init__.py` | Export | Add to imports and `__all__` |

### Where to Add New Core Logic
| Location | Type of Change | Pattern to Follow |
|----------|---------------|-------------------|
| `src/weld/core/` | New core module | See `core/plan_parser.py` |
| `src/weld/core/__init__.py` | Export | Add to imports and `__all__` |

### Where to Add New Services
| Location | Type of Change | Pattern to Follow |
|----------|---------------|-------------------|
| `src/weld/services/` | New service module | See `services/codex.py` |
| `src/weld/services/__init__.py` | Export | Add to imports and `__all__` |

### Where NOT to Modify
- `src/weld/__init__.py` - Only contains version
- Test files - Should mirror implementation structure

---

## Critical Implementation Order

Based on dependencies between features:

### Phase 1: Foundation (enables all subsequent phases)
1. **Multi-category checks** - Restructure ChecksConfig, add ChecksSummary model, update loop
2. **Run locking** - Add Lock model, create lock_manager.py
3. **Add missing TaskTypes** - DISCOVER, INTERVIEW, RESEARCH, RESEARCH_REVIEW
4. **Global CLI options** - Add --dry-run, --debug to callback

### Phase 2: Research Phase (blocks discover integration)
5. **Research models** - Add to Meta: research_version, stale_artifacts
6. **Directory structure** - Add research/ to create_run_directory()
7. **research_processor.py** - Prompt generation, similar to plan_parser.py
8. **commands/research.py** - import, review, prompt commands
9. **Update run.py** - Generate research prompt first (plan becomes step 2)

### Phase 3: Artifact Versioning (enables safe artifact updates)
10. **version_info.py model** - VersionInfo, StaleOverride, CommandEvent
11. **artifact_versioning.py** - Version management, staleness checking
12. **Update Meta model** - Add version tracking fields
13. **Modify imports** - plan_import, research_import use versioning

### Phase 4: Discover & Interview (brownfield workflow)
14. **discover.py models** - DiscoverMeta
15. **discover_engine.py** - Codebase analysis
16. **commands/discover.py** - discover command with --output
17. **interview_engine.py** - Interactive Q&A loop
18. **commands/interview.py** - interview command

### Phase 5: CLI Completion
19. **Missing run subcommands** - continue, abandon, report, history
20. **step skip and amend** - Skip marking, iter-amend directories
21. **status and doctor** - Diagnostic commands
22. **weld next shortcut** - Find and start next pending step
23. **Run selection prompt** - Interactive selection when --run omitted

### Phase 6: Templates & Polish
24. **.weldignore support** - ignore_patterns.py, init integration
25. **Custom prompt templates** - --customize flag, template loading
26. **Debug logging** - Persistent file logging, rotation
27. **Per-phase timing** - Timing model, progress display
28. **JSON schema versioning** - Wrapper with schema_version
29. **Error message improvements** - Add suggested next actions

---

## Open Questions

### Requires Human Input
- [ ] **Naming migration:** Should existing `plan.raw.md`/`plan.final.md` be migrated to `plan.md` with history?
- [ ] **TaskType naming:** Spec uses `plan`/`fix` but implementation uses `plan_generation`/`fix_generation` - standardize?
- [ ] **Default behavior:** Should `--skip-research` be default (matching current behavior) or explicit opt-in?
- [ ] **Priority:** Discover vs Interview - which is more critical for initial brownfield support?

### Requires Runtime Validation
- [ ] Interactive prompts with prompt_toolkit for keyboard shortcuts
- [ ] Rich checkbox UI for `--interactive` commit file selection
- [ ] Progress spinner display during long AI operations

### Out of Scope (noted for later)
- PR creation integration (spec doesn't cover this)
- Multiple simultaneous runs (spec explicitly prevents with locking)

---

## Appendix: Exit Code Reference

From SPECS.md, consolidated exit codes:

| Code | Meaning | Spec Lines |
|------|---------|------------|
| 0 | Success | - |
| 1 | General error / not found | - |
| 2 | Dependency missing / unauthenticated gh | 938 |
| 3 | Not a git repo | 939 |
| 4 | Stale artifact (needs regeneration) | 1265 |
| 10 | Max iterations reached without passing | 1533 |
| 12 | AI invocation failed | 1014, 1226 |
| 13 | Timeout (partial saved) | 1015 |
| 20 | No staged changes | 1643 |
| 21 | Transcript generation failed (only with --strict) | 1644 |
| 22 | Git commit failed | 1645 |

---

## Appendix: Useful Grep Patterns

```bash
# Find all command registrations
grep -n "app.command" src/weld/cli.py

# Find all exit codes used
grep -rn "raise typer.Exit" src/weld/commands/

# Find all subprocess calls
grep -rn "subprocess.run" src/weld/

# Find all Pydantic models
grep -rn "class.*BaseModel" src/weld/models/

# Find TaskType usage
grep -rn "TaskType\." src/weld/

# Find all typer.Option declarations
grep -rn "typer.Option" src/weld/commands/

# Find all config section references
grep -rn "config\." src/weld/core/
```

---

## Appendix: Current vs Spec File Naming

| Spec Name | Current Name | Location |
|-----------|--------------|----------|
| `plan.md` | `plan.raw.md`, `plan.final.md` | `run_dir/plan/` |
| `review.md` | `codex.review.md` | `iter_dir/` |
| `issues.json` | `codex.issues.json` | `iter_dir/` |
| `fix.iter<NN>.md` | `fix.prompt.iter<NN>.md` | `step_dir/prompt/` |
| `checks/<category>.txt` | `checks.txt` | `iter_dir/` |
