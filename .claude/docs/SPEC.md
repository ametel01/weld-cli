# Weld CLI - Technical Specification

## Executive Summary

Weld is a human-in-the-loop coding harness that provides structured workflows for AI-assisted software development. It bridges the gap between unstructured AI coding sessions and production-quality software engineering by enforcing research → plan → implement → commit workflows with full transcript provenance.

**Core Value Proposition:**
- Prevents AI "hallucination drift" through structured context onboarding
- Creates audit trails via transcript-linked commits
- Enables reproducible AI-assisted development workflows
- Supports both greenfield and brownfield project workflows

**Target Users:** Software engineers using AI coding assistants (Claude, Codex) who want structure, provenance, and quality gates in their AI-assisted development.

---

## Philosophy

> "If agents are not onboarded with accurate context, they will fabricate."

Weld provides structured workflows for AI-assisted development with full transcript provenance tracking. Each command produces artifacts that guide subsequent work.

> "Bad plans produce dozens of bad lines of code. Bad research produces hundreds."

Planning is highest-leverage. A solid plan dramatically constrains implementation. Solid research constrains planning.

---

## Workflows

Weld supports flexible AI-assisted workflows:

**Greenfield Projects:**
- User writes a spec document
- `weld research` to analyze codebase and requirements
- `weld plan` to create implementation plan from spec
- `weld implement` to execute plan with AI assistance
- `weld commit` to create commits with transcript provenance

**Brownfield Projects:**
- `weld discover` to reverse-engineer codebase into architecture spec
- `weld interview` (optional) to refine the generated spec
- User writes feature spec referencing architecture
- Continue with research → plan → implement → commit

**Document Review:**
- `weld review` for code review or document analysis

```
GREENFIELD WORKFLOW
───────────────────────────────────────────────────────────

  [User writes spec.md]
           │
           ▼
  ┌─────────────────┐     ┌─────────────────┐
  │ weld interview  │◄───►│   spec.md       │ (optional)
  │ spec.md         │     │   refined       │
  └────────┬────────┘     └─────────────────┘
           │
           ▼
  ┌─────────────────┐
  │ weld research   │ ─── Analyze requirements and codebase
  │ spec.md         │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ weld plan       │ ─── Create implementation plan
  │ spec.md         │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ weld implement  │ ─── Execute plan with AI
  │ plan.md         │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ weld commit     │ ─── Commit with transcript
  └─────────────────┘

───────────────────────────────────────────────────────────

BROWNFIELD WORKFLOW
───────────────────────────────────────────────────────────

  ┌─────────────────┐
  │ weld discover   │ ─── Analyzes entire codebase
  └────────┬────────┘     (generates architecture.md)
           │
           ▼
  ┌─────────────────┐     ┌─────────────────┐
  │ weld interview  │────►│ architecture.md │ (optional)
  │ architecture.md │     │   refined       │
  └─────────────────┘     └─────────────────┘
           │
           ▼
  ┌─────────────────────────────────┐
  │ User writes feature-spec.md    │
  │ (references architecture.md)   │
  └────────────────┬────────────────┘
                   │
                   ▼
           Continue with greenfield workflow

───────────────────────────────────────────────────────────
```

**Each command is standalone:** No automated workflow orchestration. User explicitly invokes each command in sequence.

---

## Detailed Requirements

### Functional Requirements

#### FR-1: Project Initialization (`weld init`)
- **FR-1.1:** Create `.weld/` directory structure with subdirectories for discover, research, plan, and sessions
- **FR-1.2:** Generate default `config.toml` with sensible defaults
- **FR-1.3:** Detect project type (Python, Node.js, etc.) and offer to create `.weldignore` with appropriate defaults
- **FR-1.4:** Validate toolchain availability (git, gh, claude) with version recommendations
- **FR-1.5:** Support monorepo detection - allow `.weld/` per subdirectory based on cwd

**Exit codes:**
- `0` - Success
- `2` - Missing dependencies
- `3` - Not a git repository

#### FR-2: Codebase Discovery (`weld discover`)
- **FR-2.1:** Analyze source code structure excluding patterns in `.weldignore`
- **FR-2.2:** Generate markdown architecture documentation with `file:line` references
- **FR-2.3:** Save output to `.weld/discover/<timestamp>/output.md`
- **FR-2.4:** Stream raw Claude output during operation
- **FR-2.5:** Support checkpoint intermediate results for resumability

**Options:**
- `--output PATH` - Where to write the architecture spec (prompts if omitted)

**Behavior:**
- Respects `.weldignore` patterns
- Excludes tests and dependencies
- Optionally launches interview for refinement

**Exit codes:**
- `0` - Success
- `1` - No source files found
- `12` - AI invocation failed

#### FR-3: Document Interview (`weld interview`)
- **FR-3.1:** Accept any markdown file as input for interactive refinement
- **FR-3.2:** AI asks clarifying questions one at a time, adapting based on answers
- **FR-3.3:** Explicitly flag contradictions between user answers and existing document content
- **FR-3.4:** Update document in-place when refinement complete
- **FR-3.5:** Support `--focus` option to limit questions to specific topic area

**Arguments:**
- `FILE` - Path to markdown file to refine

**Options:**
- `--focus TOPIC` - Limit questions to specific topic area

**Exit codes:**
- `0` - Success
- `1` - File not found
- `2` - User cancelled

#### FR-4: Requirements Research (`weld research`)
- **FR-4.1:** Read specification file and analyze relevant codebase areas
- **FR-4.2:** Document findings, patterns, and technical considerations
- **FR-4.3:** Save to `.weld/research/<timestamp>/output.md`

**Arguments:**
- `SPEC_FILE` - Path to specification markdown file

**Exit codes:**
- `0` - Success
- `1` - Spec file not found
- `12` - AI invocation failed

#### FR-5: Implementation Planning (`weld plan`)
- **FR-5.1:** Generate phased implementation plan from specification
- **FR-5.2:** If research exists for spec, add reference paths to research doc with section citations
- **FR-5.3:** Validate generated plan has correct structure (phases have steps, steps have goals)
- **FR-5.4:** Save to `.weld/plan/<timestamp>/output.md`
- **FR-5.5:** Support checkpoint intermediate for resumability

**Arguments:**
- `SPEC_FILE` - Path to specification markdown file

**Plan Format:**
```markdown
## Phase N: <Title>

Description of phase goals

### Phase Validation
```bash
# Commands to verify phase completion
```

### Step N: <Title>

#### Goal
What this step accomplishes

#### Files
- `path/to/file` - Changes to make

#### Validation
```bash
# Command to verify step
```

#### Failure modes
- Potential issues and detection
```

**Exit codes:**
- `0` - Success
- `1` - Spec file not found
- `12` - AI invocation failed

#### FR-6: Plan Execution (`weld implement`)
- **FR-6.1:** Parse plan file and present interactive menu (arrows + enter, escape to cancel)
- **FR-6.2:** Support `--step N.M` and `--phase N` for non-interactive execution
- **FR-6.3:** Invoke Claude to implement selected phase/step
- **FR-6.4:** Mark completed items with **COMPLETE** marker in plan file
- **FR-6.5:** After step completes, prompt user whether to run validation commands
- **FR-6.6:** On Ctrl+C interruption, leave partial changes in working directory as-is
- **FR-6.7:** Session tracking always enabled for implement operations
- **FR-6.8:** Offer interactive repair for malformed plan files (auto-fix or launch $EDITOR)

**Arguments:**
- `PLAN_FILE` - Path to implementation plan markdown

**Options:**
- `--step STEP` - Execute specific step non-interactively (e.g., "1.2")
- `--phase PHASE` - Execute all steps in phase non-interactively
- `--quiet` - Suppress streaming output
- `--timeout SECONDS` - Override default timeout

**Behavior:**
- **Interactive mode** (default): Arrow-key menu to select phase/step
- **Non-interactive mode** (`--step`/`--phase`): Execute specified item
- **Automatically tracks file changes for session-based commits**
- Graceful interruption: Ctrl+C saves progress

**Important: No Conversational Context Between Steps**

Each step execution is an independent Claude CLI invocation with NO shared conversational
context:

- When a step is executed, `run_claude()` spawns a fresh Claude process with a prompt
  containing only that step's specification
- Each Claude invocation is stateless - it has no memory of previous steps
- The interactive menu loop is just the `weld implement` process continuing, not a
  continued Claude conversation
- Step prompts must be self-contained because each execution starts fresh

**Session Tracking vs. Conversational Context**

The distinction between session tracking and conversational context is critical:

- **Session tracking** (`track_session_activity()`): Wraps the entire `weld implement`
  command to record file changes for commit grouping. All steps share one session ID
  for commit provenance purposes.
- **Conversational context**: Does NOT exist between steps. Each `run_claude()` call
  is independent with no shared state.

**Example:** When implementing a 3-step plan:
```
weld implement plan.md
├─ Step 1 execution: Fresh Claude CLI process → completes → exits
├─ Menu displays
├─ Step 2 execution: NEW fresh Claude CLI process → completes → exits
├─ Menu displays
└─ Step 3 execution: NEW fresh Claude CLI process → completes → exits
```

All three executions are tracked under one session ID (for commit grouping), but each
is a separate, independent Claude invocation with no conversational memory.

**Exit codes:**
- `0` - Success
- `1` - Plan file not found or invalid
- `12` - AI invocation failed

#### FR-7: Transcript-Linked Commits (`weld commit`)
- **FR-7.1:** Group staged files by originating Claude Code session (last session wins for multi-session files)
- **FR-7.2:** Generate semantic commit messages via Claude
- **FR-7.3:** Render transcript from session JSONL with redaction and truncation
- **FR-7.4:** Upload transcript to GitHub Gist, add `Claude-Transcript:` trailer
- **FR-7.5:** If gist upload fails, commit without trailer and warn user
- **FR-7.6:** Update CHANGELOG.md in Keep a Changelog format
- **FR-7.7:** If CHANGELOG doesn't match format, offer to convert or create new
- **FR-7.8:** If no staged changes but unstaged exist, offer to stage all
- **FR-7.9:** Auto-prune committed sessions from registry
- **FR-7.10:** Create separate "manual changes" commit for files not tracked by any session

**Options:**
- `-a, --all` - Stage all changes before committing
- `--no-split` - Force single commit (disable logical grouping)
- `--no-session-split` - Disable session-based grouping
- `--skip-transcript` - Skip transcript upload
- `--skip-changelog` - Skip CHANGELOG.md update
- `-q, --quiet` - Suppress streaming output

**Behavior:**
1. Groups staged files by originating Claude session (default)
2. For each session: generates commit message via Claude
3. Renders transcript from session JSONL
4. Uploads transcript to GitHub Gist
5. Creates commit with `Claude-Transcript: <gist-url>` trailer
6. Updates CHANGELOG.md in Keep a Changelog format

**Fallback:** If no sessions tracked, creates commits based on logical grouping

**Exit codes:**
- `0` - Success
- `3` - Not a git repository
- `20` - No staged changes
- `22` - Git commit failed

#### FR-8: Document Review (`weld review`)
- **FR-8.1:** Support `--focus code` for code review mode
- **FR-8.2:** Support `--focus doc` for document review mode (default)
- **FR-8.3:** Use configured review provider per task_models config

**Arguments:**
- `FILE` - Path to file to review

**Options:**
- `--focus MODE` - Review mode: `code` or `doc` (default: doc)

**Exit codes:**
- `0` - Success
- `1` - File not found
- `12` - AI invocation failed

#### FR-9: Environment Diagnostics (`weld doctor`)
- **FR-9.1:** Check tool availability (git, gh, claude, codex)
- **FR-9.2:** Check for recommended versions, warn if below recommended
- **FR-9.3:** Validate GitHub CLI authentication
- **FR-9.4:** Validate config file syntax and schema
- **FR-9.5:** Check directory permissions

**Checks:**
- Tool availability (git, gh, claude, codex)
- GitHub CLI authentication
- Config file validity
- Directory permissions

**Exit codes:**
- `0` - All checks passed
- `1` - One or more checks failed

#### FR-10: Command History (`weld <command> history`)
- **FR-10.1:** `weld discover history` - View discover command history
- **FR-10.2:** `weld research history` - View research command history
- **FR-10.3:** `weld plan history` - View plan command history

**Behavior:**
- Displays timestamped list of command runs
- Shows output paths and completion status

### Non-Functional Requirements

#### NFR-1: Performance
- **NFR-1.1:** No file count or size limits for discover operations (user controls via .weldignore)
- **NFR-1.2:** Transcript size limit: 10MB default, truncate large tool outputs and thinking blocks
- **NFR-1.3:** All subprocess calls have timeouts (see Subprocess Timeouts table)
- **NFR-1.4:** No AI response caching - artifacts serve as manual cache

#### NFR-2: Security
- **NFR-2.1:** Never use `shell=True` in subprocess calls
- **NFR-2.2:** Value-only secret redaction in transcripts, preserving JSON/YAML structure
- **NFR-2.3:** Heuristic filtering for false positives (entropy analysis, test value patterns)
- **NFR-2.4:** Full debug logging allowed (user-controlled, not auto-transmitted)
- **NFR-2.5:** No telemetry - fully offline operation

#### NFR-3: Reliability
- **NFR-3.1:** Support checkpoint intermediate results for long operations
- **NFR-3.2:** Graceful Ctrl+C handling preserves partial work
- **NFR-3.3:** Prompt for config/artifact format migrations, don't auto-migrate silently
- **NFR-3.4:** `--dry-run` validates inputs (files exist, config valid) without execution

#### NFR-4: Usability
- **NFR-4.1:** Stream raw Claude output during operations (no progress bars)
- **NFR-4.2:** Minimal keyboard navigation (arrows, enter, escape)
- **NFR-4.3:** Basic Typer-generated shell completions
- **NFR-4.4:** Git serves as rollback mechanism - no weld-specific undo
- **NFR-4.5:** No hooks/extensibility - users wrap weld in their own scripts

#### NFR-5: Testability
- **NFR-5.1:** 70% code coverage requirement
- **NFR-5.2:** All AI CLI calls mocked in unit tests, no real AI in CI
- **NFR-5.3:** Test markers: `@pytest.mark.unit`, `@pytest.mark.cli`, `@pytest.mark.slow`

---

## Technical Architecture & Design Decisions

### Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI Layer (cli.py)                     │
│         Typer entry point, global options, routing          │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                 Commands Layer (commands/)                   │
│     Thin handlers: parse args, validate, delegate           │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Core Layer (core/)                        │
│    Business logic: history, plan parsing, engines           │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                Services Layer (services/)                    │
│   External integrations: git, claude, gist, transcripts     │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                 Models Layer (models/)                       │
│         Pydantic data models for validation                 │
└─────────────────────────────────────────────────────────────┘
```

### Session Management Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    Session Lifecycle                            │
└────────────────────────────────────────────────────────────────┘

1. Detection (session_detector.py)
   ├── Scan ~/.claude/projects/ for .jsonl files
   ├── Track ALL active sessions (support concurrent instances)
   ├── Map sessions to repository via working directory
   └── Extract session ID (UUID) from filename

2. Tracking (session_tracker.py)
   ├── Record file changes (created/modified) per command
   ├── Store in .weld/sessions/registry.jsonl
   ├── Last session wins for multi-session file attribution
   └── Support monorepo: .weld/ per subdirectory based on cwd

3. Commit Grouping (commit.py)
   ├── Load registry, group staged files by session
   ├── Generate commit per session with transcript gist
   ├── Create separate commit for untracked files (manual changes)
   └── Auto-prune committed sessions from registry

4. Transcript Generation (transcript_renderer.py)
   ├── Parse session JSONL
   ├── Apply redaction (value-only, heuristic filtering)
   ├── Summarize thinking blocks: "[Thinking: ~N tokens]"
   ├── Enforce 10MB size limit with truncation
   └── Upload via gh gist create
```

### Data Flow Diagrams

**Research → Plan Flow:**
```
┌──────────────┐     ┌─────────────────┐     ┌────────────────┐
│   spec.md    │────►│ weld research   │────►│ research.md    │
└──────────────┘     └─────────────────┘     └────────────────┘
                                                     │
                                                     │ reference path
                                                     ▼
┌──────────────┐     ┌─────────────────┐     ┌────────────────┐
│   spec.md    │────►│   weld plan     │────►│   plan.md      │
└──────────────┘     └─────────────────┘     │ (cites research│
                                             │  sections)     │
                                             └────────────────┘
```

**Commit Flow:**
```
┌────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Staged    │────►│  Group by        │────►│ Session A files │
│  Files     │     │  Session         │     │ Session B files │
└────────────┘     └──────────────────┘     │ Untracked files │
                                            └─────────────────┘
                                                     │
                   ┌─────────────────────────────────┼──────────┐
                   ▼                                 ▼          ▼
           ┌─────────────┐               ┌────────────┐  ┌────────────┐
           │ Render      │               │ Render     │  │ Manual     │
           │ Transcript A│               │ Transcript │  │ Commit     │
           └─────────────┘               │ B          │  │ (no gist)  │
                   │                     └────────────┘  └────────────┘
                   ▼
           ┌─────────────┐
           │ Upload Gist │──── Fails? ────► Commit without trailer
           └─────────────┘
                   │ Success
                   ▼
           ┌─────────────────────────────────────┐
           │ Commit with Claude-Transcript: URL  │
           └─────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Config location | Repo-only (.weld/config.toml) | Simplicity; users add sensitive values to .gitignore |
| Session attribution | Last session wins | Simpler mental model; most recent work is most relevant |
| Secret redaction | Value-only with heuristics | Preserves structure for debugging while protecting secrets |
| Thinking blocks | Summarize as "[Thinking: ~N tokens]" | Balance transparency and readability |
| AI response caching | No caching | Artifacts serve as manual cache; avoids stale responses |
| Extensibility | No hooks | Keep scope minimal; users wrap weld externally |
| Undo mechanism | Git is rollback | Leverage existing git primitives |
| Progress feedback | Stream raw output | Direct visibility into AI reasoning |
| Monorepo support | .weld/ per subdirectory | Auto-detect based on cwd |

---

## Hard Requirements

* Python **3.11+**
* Package manager: **`uv` only** (strict requirement)
  * No pip/poetry/pipenv workflows in docs or tooling
* Build backend: **`hatchling`**
* External CLIs available in PATH:
  * `git` - Version control operations
  * `gh` - GitHub CLI (authenticated) for gist uploads
  * `claude` - Claude CLI for AI operations (optional, can configure other providers)
  * `codex` - Codex CLI (optional, can configure other providers)

**Note:** Transcript generation is now native (no external binary required). Uses Claude session files from `~/.claude/projects/`.

---

## Session Tracking and Transcripts

Weld tracks Claude Code session activity during `weld implement` commands,
enabling session-based commit grouping with transcript provenance.

### Session Detection

Automatically detects active Claude Code session from `~/.claude/projects/`:
- Finds most recently modified `.jsonl` session file
- Extracts session ID from filename (UUID)
- Links session to repository for tracking

### Session Registry

`.weld/sessions/registry.jsonl` stores tracked sessions:
- Each session maps to a Claude Code session ID
- Records file changes (created/modified) from implement commands
- Tracks command execution and completion status
- Used to group commits by originating session

### Automatic Tracking

`weld implement` automatically tracks file changes:
- No flag needed - tracking is always enabled
- Records files created/modified during step execution
- Marks activity as complete or incomplete (on Ctrl+C)
- Gracefully handles missing Claude session (skips tracking)

### Transcript Generation

Native rendering from Claude session JSONL files:
- **Redaction:** API keys, tokens, credentials removed
- **Truncation:** Large tool results and thinking blocks truncated
- **Size limits:** Per-message and total transcript size limits
- **Upload:** Via `gh gist create` to GitHub Gists

### Session-Based Commits

`weld commit` groups staged files by session:
1. Loads session registry to map files → sessions
2. Creates one commit per session with transcript gist attached
3. Untracked files handled interactively (attribute or separate commit)
4. Prunes committed sessions from registry
5. Falls back to logical grouping if no sessions tracked

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

## Repository Layout

```
repo/
  pyproject.toml
  .python-version
  .weldignore                     # File ignore patterns (gitignore-style)
  CHANGELOG.md                    # Keep a Changelog format (auto-updated)
  .weld/
    config.toml                   # Configuration file
    debug.log                     # Debug log (if enabled)
    sessions/
      registry.jsonl              # Session tracking registry
    discover/
      history.jsonl               # Discover command history
      <timestamp>/                # Timestamped discover outputs
        output.md                 # Generated architecture spec
    research/
      history.jsonl               # Research command history
      <timestamp>/                # Timestamped research outputs
        output.md                 # Research artifact
    plan/
      history.jsonl               # Plan command history
      <timestamp>/                # Timestamped plan outputs
        output.md                 # Implementation plan

  src/weld/
    __init__.py
    cli.py                        # Typer CLI entry point
    config.py                     # WeldConfig, TaskModelsConfig
    logging.py                    # Logging configuration
    output.py                     # OutputContext for console/JSON
    commands/                     # CLI command handlers
      __init__.py
      init.py                     # weld init
      discover.py                 # weld discover
      interview.py                # weld interview
      research.py                 # weld research
      plan.py                     # weld plan
      implement.py                # weld implement
      commit.py                   # weld commit
      doc_review.py               # weld review
      doctor.py                   # weld doctor
    core/                         # Business logic
      __init__.py
      weld_dir.py                 # .weld directory utilities
      history.py                  # JSONL command history
      plan_parser.py              # Phased plan parsing (Phase, Step, Plan)
      discover_engine.py          # Codebase discovery prompts
      interview_engine.py         # Specification refinement prompts
      doc_review_engine.py        # Document review prompts
    services/                     # External integrations
      __init__.py
      git.py                      # Git operations (never shell=True)
      claude.py                   # Claude CLI integration with streaming
      filesystem.py               # File system operations
      session_detector.py         # Auto-detect Claude Code sessions
      session_tracker.py          # Track file changes per session
      transcript_renderer.py      # Render JSONL to markdown
      gist_uploader.py            # Upload transcripts via gh CLI
      transcripts.py              # Legacy transcript tool wrapper
    models/                       # Pydantic data models
      __init__.py
      session.py                  # SessionActivity, TrackedSession
      discovery.py                # DiscoverMeta
      issues.py                   # Issue, Issues models
```

---

## CLI Contract

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
* `--dry-run` - Preview effects without applying (validates inputs only)
* `--debug` - Enable debug logging for this invocation

---

## User Experience Specifications

### Interactive Menu (weld implement)

**Keyboard Controls:**
- `↑` / `↓` - Navigate between phases/steps
- `Enter` - Select and execute
- `Escape` - Cancel and return to previous menu

**Menu Display:**
```
┌─────────────────────────────────────────┐
│ Select phase or step to implement:      │
├─────────────────────────────────────────┤
│ ▸ Phase 1: Database Schema              │
│     Step 1.1: Create migrations         │
│     Step 1.2: Add models ✓ COMPLETE     │
│   Phase 2: API Endpoints                │
│     Step 2.1: User endpoints            │
└─────────────────────────────────────────┘
```

### Progress Feedback

During long-running operations, weld streams raw Claude output:

```
$ weld discover
Analyzing codebase...

[Claude streaming output appears here in real-time]

✓ Architecture spec saved to .weld/discover/20240115_143022/output.md
```

### Error States

**Plan Parse Error (Interactive Repair):**
```
$ weld implement plan.md
⚠ Plan file has formatting issues:
  - Line 45: Missing step number
  - Line 72: Invalid phase marker

Options:
  [A] Auto-fix (attempt automatic repair)
  [E] Edit (open in $EDITOR)
  [C] Cancel

Choice: _
```

**Gist Upload Failure:**
```
$ weld commit
Generating commit for Session abc123...
⚠ Gist upload failed: Network timeout
  Creating commit without Claude-Transcript trailer

✓ Committed: "Add user authentication" (no transcript)
```

---

## Edge Cases & Error Handling

### Session Management

| Scenario | Behavior |
|----------|----------|
| Multiple concurrent Claude instances | Track all sessions; user chooses during commit |
| File modified by multiple sessions | Last session wins (most recent modification) |
| File not tracked by any session | Create separate "manual changes" commit |
| Session registry corrupted | Rebuild from git history + Claude logs |

### Transcript Generation

| Scenario | Behavior |
|----------|----------|
| Transcript exceeds 10MB | Truncate large tool outputs, then thinking blocks |
| Secret pattern false positive | Heuristic filtering: skip low-entropy, test values |
| Gist upload fails | Commit proceeds without trailer, warning shown |
| Thinking blocks present | Replace with "[Thinking: ~N tokens]" summary |

### Plan Execution

| Scenario | Behavior |
|----------|----------|
| Plan file malformed | Offer interactive repair (auto-fix or $EDITOR) |
| Step fails validation | Mark as incomplete, prompt user for next action |
| Ctrl+C during execution | Leave partial changes in working directory |
| No research exists | Plan proceeds without research reference |

### Configuration

| Scenario | Behavior |
|----------|----------|
| Config schema changed | Prompt user before migration, don't auto-migrate |
| CHANGELOG wrong format | Offer to convert or create new |
| Tool below recommended version | Warn but allow operation |
| Monorepo detected | Support .weld/ per subdirectory based on cwd |

---

## UX Behavior

* **Direct AI invocation**: Claude CLI invoked directly with streaming output
* **Artifact-driven**: Commands produce timestamped markdown artifacts
* **Automatic tracking**: `weld implement` automatically records file changes for session-based commits
* **Everything inspectable**: All artifacts stored under `.weld/` with JSONL history
* **Global options**: All commands support `--dry-run`, `--json`, `--debug`, `--quiet`
* **Progress feedback**: Long-running operations show streaming output
* **Interactive menus**: `implement` command uses arrow-key navigation (simple-term-menu)
* **Graceful interruption**: Ctrl+C in `implement` saves progress
* **Session-based commits**: Files grouped by originating Claude session
* **AI-generated commit messages**: Semantic messages via Claude, trailers for provenance
* **CHANGELOG integration**: Auto-updates CHANGELOG.md in Keep a Changelog format

---

## Testing Strategy

### Test Categories

**Unit Tests (`@pytest.mark.unit`):**
- All core business logic (plan parsing, session tracking, redaction)
- All external CLI calls mocked
- Fast execution (<1s per test)

**CLI Tests (`@pytest.mark.cli`):**
- Command-line argument parsing
- Output formatting (console, JSON)
- Exit codes
- Uses CliRunner fixture with NO_COLOR=1

**Slow Tests (`@pytest.mark.slow`):**
- File system operations with temp_git_repo fixture
- Complex workflows spanning multiple commands

### Testing Patterns

- Use `runner` fixture (CliRunner) for CLI tests with NO_COLOR=1
- Use `temp_git_repo` fixture for git-dependent tests (auto-configures user, creates initial commit)
- Subprocess safety: All external commands use `subprocess.run()` with `check=True`, `capture_output=True`, `timeout=N`
- Mock external CLIs (`claude`, `gh`) in unit tests; integration tests marked with `@pytest.mark.cli`

### Mocking Strategy

```python
# All AI CLI calls mocked in unit tests
@pytest.fixture
def mock_claude(mocker):
    return mocker.patch("weld.services.claude.invoke", return_value=MockResponse())

@pytest.fixture
def mock_gh(mocker):
    return mocker.patch("weld.services.gist_uploader.upload", return_value="https://gist.github.com/...")
```

### Coverage Requirements

- Overall: 70% minimum
- Services layer: 80% minimum (critical external integrations)
- Core layer: 85% minimum (business logic)

---

## Installation and Execution

### Create environment and install editable

```bash
uv venv
uv pip install -e .
```

### Run

```bash
weld init
weld discover --output docs/architecture.md
```

---

## Example Workflows

### Greenfield E2E Flow

```bash
# Setup
uv venv
uv pip install -e .
weld init

# User creates spec.md externally with requirements

# Research phase (optional)
weld research specs/feature.md
# Output: .weld/research/<timestamp>/output.md

# Plan phase
weld plan specs/feature.md
# Output: .weld/plan/<timestamp>/output.md

# Implementation
weld implement .weld/plan/<timestamp>/output.md
# Interactive menu to select phases/steps
# Marks completed items in plan file
# Automatically tracks file changes for session-based commits

# Commit with transcript
git add .
weld commit
# Creates commit(s) grouped by Claude session
# Uploads transcript gist and adds trailer
# Updates CHANGELOG.md
```

### Brownfield E2E Flow

```bash
weld init

# Discover existing codebase
weld discover --output docs/architecture.md
# Generates architecture documentation

# Optionally refine the spec
weld interview docs/architecture.md

# User creates feature spec referencing architecture
# specs/new-feature.md

# Continue with standard workflow
weld research specs/new-feature.md
weld plan specs/new-feature.md
weld implement .weld/plan/<timestamp>/output.md
git add .
weld commit
```

### Document Review Flow

```bash
# Review code for issues
weld review src/module.py --focus code

# Review documentation for clarity
weld review docs/guide.md --focus doc
```

### Diagnostics

```bash
# Check tool availability and config
weld doctor

# View command history
weld discover history
weld research history
weld plan history
```

### Result Artifacts

After successful execution:

* `.weld/research/<timestamp>/output.md` - Research findings
* `.weld/plan/<timestamp>/output.md` - Implementation plan with **COMPLETE** markers
* `.weld/sessions/registry.jsonl` - Session tracking for commits
* Git commits with `Claude-Transcript: <gist-url>` trailers
* Updated `CHANGELOG.md` in Keep a Changelog format

---

## Configuration

### Full Configuration Schema

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

[transcripts]
enabled = true
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
plan_generation = { provider = "claude" }
plan_review = { provider = "codex" }
implementation = { provider = "claude" }
implementation_review = { provider = "codex" }
fix_generation = { provider = "claude" }

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
- `plan_generation` - Generating plan from spec (default: claude)
- `plan_review` - Reviewing plan (default: codex)
- `implementation` - Implementing steps (default: claude)
- `implementation_review` - Reviewing implementations (default: codex)
- `fix_generation` - Generating fix prompts for failed implementations (default: claude)

Each task can specify a `provider`, optional `model`, and optional `exec` path override.

**Note:** Defaults are examples only - user should configure based on their preference. Any provider can be used for any task.

### Notes

* Check commands are parsed via `shlex.split()` and executed without shell (no `shell=True`)
* Credentials are validated lazily when each provider is first invoked

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

## Success Metrics

### Adoption Metrics
- Number of `weld init` executions (new project setups)
- Number of commits with Claude-Transcript trailers
- Ratio of transcript-linked vs non-linked commits

### Quality Metrics
- Plan structural validation pass rate
- Secret redaction accuracy (no leaked secrets in gists)
- Gist upload success rate

### Workflow Metrics
- Average steps per plan execution
- Completion rate of generated plans
- Time from spec to first commit

---

## Open Questions & Future Considerations

### Deferred Features
1. **AI response caching** - Could reduce API costs for unchanged specs
2. **Hook system** - Pre/post command scripts for customization
3. **Team collaboration** - Shared session tracking across team members
4. **Plan templates** - Pre-built plan structures for common patterns

### Technical Debt to Monitor
- JSONL format evolution may require migration support
- Claude CLI API changes may break integration
- GitHub Gist API rate limits may need fallback strategy

### Migration Path Considerations
- Session registry format changes require backward-compatible readers
- Config schema changes should support N-1 version compatibility
- Artifact format changes may need converter utilities

---

## Key Principles

* **Commands are standalone** - Each command runs independently, no complex workflow orchestration
* **Artifacts over state** - Commands produce markdown artifacts (research, plan, etc.)
* **Session tracking** - File changes tracked per Claude Code session for transcript generation
* **Flexible AI providers** - Configure which model (Claude/Codex/etc.) handles each task type
* **Transcript provenance** - Commits include gist URLs linking to full AI interaction history
* **Global options** - All commands support `--dry-run`, `--json`, `--debug`, etc.

---

## Appendix A: Secret Redaction Patterns

### Detected Patterns
- API keys: `[A-Za-z0-9_-]{20,}` with high entropy
- AWS keys: `AKIA[A-Z0-9]{16}`
- JWT tokens: `eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`
- GitHub tokens: `gh[pousr]_[A-Za-z0-9]{36,}`
- Generic secrets: Keys containing password, secret, token, credential

### Heuristic Filtering (Not Redacted)
- Low entropy strings (<3.0 bits per char)
- Known test values: `test-key`, `xxx`, `placeholder`, `example`
- Environment-specific markers: `$VARIABLE`, `<PLACEHOLDER>`

---

## Appendix B: Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error (file not found, invalid input) |
| 2 | Missing dependencies / user cancelled |
| 3 | Not a git repository |
| 12 | AI invocation failed |
| 20 | No staged changes |
| 22 | Git commit failed |

---

## Appendix C: pyproject.toml (uv-native with hatchling)

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
