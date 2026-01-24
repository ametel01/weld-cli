# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Shell completion for step numbers in CLI commands

### Added
- Shell completion for markdown file arguments in CLI commands

### Added
- Shell completion for export format options in prompt export command

### Added
- Shell completion support for task type arguments in CLI commands

### Added
- `run_claude_interactive` service function for fully interactive Claude sessions

### Added
- `run_claude_interactive` function for terminal-connected Claude sessions

### Changed
- `weld interview` overhauled to use two-step questionnaire workflow
  - `weld interview generate <spec.md>` - generates questionnaire with multiple-choice questions
  - `weld interview apply <questionnaire.md>` - applies user's answers to update spec
  - Questionnaires saved to `.weld/interviews/` with timestamped filenames
  - Users mark answers with `[x]` in markdown checkboxes before applying
  - Replaces previous interactive session approach which had terminal compatibility issues

## [0.11.1] - 2026-01-24

### Changed
- `weld interview` overhauled to use two-step questionnaire workflow
  - `weld interview generate <spec.md>` - generates questionnaire with multiple-choice questions
  - `weld interview apply <questionnaire.md>` - applies user's answers to update spec
  - Questionnaires saved to `.weld/interviews/` with timestamped filenames
  - Users mark answers with `[x]` in markdown checkboxes before applying
  - Replaces previous interactive session approach which had terminal compatibility issues

## [0.11.0] - 2026-01-24

### Added
- Documentation for `weld prompt` command to manage prompt customizations
- prompt personalization system for customizing weld command prompts
  - Configure via `[prompts]` section in `.weld/config.toml`
  - Global prefix/suffix applied to all prompts
  - Per-task prefix, suffix, and default_focus settings
  - Layered application: global_prefix → task_prefix → prompt → task_suffix → global_suffix
  - Includes example customizations in generated config template
- prompt viewer command `weld prompt` for managing prompt customizations
  - `weld prompt list`: Show all task types with customization status
  - `weld prompt show <type>`: Display customization details for a task type
  - `weld prompt show --raw`: Output raw template (pipe-friendly)
  - `weld prompt show --focus`: Preview with specific focus value
  - `weld prompt export <dir> --raw`: Export all templates as markdown files
  - `weld prompt export --format toml/json`: Export customizations as config

## [0.10.0] - 2026-01-24

### Added
- Telegram bot support is now included by default (no longer requires `telegram` extra)
- Telegram bot extended prompt detection for y/n confirmations, default prompts ([Y/n], [y/N]), Continue?/Proceed?/Apply? questions, and arrow-key menus
- Universal `/weld <command>` for running any weld subcommand via Telegram
- Document upload handling with automatic save to `.weld/telegram/uploads/`
- Reply-to-document auto-injection of uploaded file path in commands
- Output file detection with Download button for created files
- Project sync method for Telegram bot to synchronize config projects with database on startup
- Telegram bot: runs table pruning to limit stored runs per user
- Telegram user management commands: `weld telegram user add/remove/list`
- Auto-prompt to install weld globally during `weld telegram init`
- `--skip-hooks` flag for `weld commit` to bypass pre-commit hooks (useful for Telegram bot or CI)
- Interactive prompt support in Telegram bot with inline keyboard buttons for command options
- `weld telegram whoami` command to show bot identity and authentication status
- `weld telegram doctor` command to validate Telegram bot setup and environment
- `weld telegram projects add` command to register projects for Telegram bot access
- `weld telegram projects remove` command to unregister projects
- `weld telegram projects list` command to show registered projects
- `weld telegram` command group for remote bot interaction
- Telegram bot commands: /doctor, /plan, /interview, /implement, /commit for remote weld execution
- Telegram bot `/status` command to view current run, queue, and recent history
- Telegram bot `/cancel` command to abort active runs and clear pending queue
- `/use` command for Telegram bot to switch between configured projects
- Rate-limited message editor for Telegram with exponential backoff retry
- Telegram message formatting utilities with proper Unicode chunking support
- Per-chat FIFO queue system for Telegram bot to ensure ordered run processing
- Async command runner for Telegram bot with streaming output and timeout handling
- `TelegramFileError` and `TelegramRunError` exception classes for more specific error handling in Telegram bot
- File path validation for Telegram bot `/fetch` and `/push` commands with path traversal protection
- SQLite state persistence for Telegram bot with user contexts, projects, and command run tracking
- Telegram bot configuration with user authentication and project registration
- Initial Telegram bot integration module structure

### Changed
- `weld plan` default output now saves to same directory as input file with `_PLAN.md` suffix
  - Example: `weld plan /path/to/SPEC.md` → `/path/to/SPEC_PLAN.md`
  - Previously saved to `.weld/plan/{filename}-{timestamp}.md`
- `weld implement --autopilot` now respects `--no-review` flag (previously ignored)
- `weld implement --autopilot` now displays all active options (autopilot, auto-commit, no-review)
- Telegram support is now included in standard installation (no longer requires `weld[telegram]` extra)

### Fixed
- Telegram bot status output now shows error messages instead of truncating them
- Telegram bot now shows clear feedback after selecting prompt options ("Command continuing...")
- Telegram bot prompt message is updated with final result when command completes
- Telegram bot now persists `started_at` timestamp when run transitions from pending to running

## [0.9.1] - 2026-01-17

### Added
- `weld plan` now accepts multiple specification files
  - Combines all specs into a single implementation plan
  - Usage: `weld plan spec1.md spec2.md spec3.md`

## [0.9.0] - 2026-01-17

### Added
- Early input validation with helpful error hints for all commands
  - Validates file paths before starting expensive operations (prevents wasted API tokens)
  - Clear error messages indicate what's wrong (e.g., "is a directory, expected a file")
  - Actionable hints suggest corrections (e.g., "Provide a file path: --output /path/output.md")
  - Applies to: `plan`, `research`, `discover`, `review`, `interview`, `implement`

### Changed
- `weld init` now adds simple `.weld/` entry to `.gitignore` instead of complex pattern
  - Previously used `.weld/*` with `!.weld/config.toml` exception to track config
  - Now ignores entire `.weld/` directory (config is local-only)

## [0.8.0] - 2026-01-14

### Added
- `--autopilot` flag for `weld implement` command
  - Executes all plan steps automatically without user intervention
  - After each step: runs code review with auto-fix, then commits
  - Stops on first Claude failure
  - Designed for CI/automation and unattended execution

### Changed
- `--dangerously-skip-permissions` now defaults to `True` for `weld plan` command
  - Plans are generated without permission prompts by default
  - Use `--no-dangerously-skip-permissions` to restore previous behavior
- All Claude CLI invocations now use `skip_permissions=True` for smoother automated workflows

### Fixed
- Plan prompt template restructured with explicit WRONG/CORRECT format examples
  - Shows concrete anti-pattern to avoid (bullet-point summaries)
  - Provides complete correct example with all required sections
  - Adds output format checklist as final reminder before generation
  - Explicitly forbids questions, follow-up options, and conversational closing
  - Clarifies CLI context: output goes directly to file, not interactive chat

## [0.7.1] - 2026-01-11

### Fixed
- `weld plan` now produces more consistent output following `docs/reference/plan-format.md`
  - Clearer template structure reduces Claude deviations from required format
  - Complete Phase 2 example ensures all phases get proper Goal/Files/Validation/Failure modes sections

## [0.7.0] - 2026-01-11

### Added
- `--dangerously-skip-permissions` flag for `weld plan` command
  - Allows Claude to explore codebase (read files, search patterns) during plan generation
  - Required when Claude needs file access to create comprehensive plans
  - Matches behavior of `weld implement` command
- `--no-review` flag for `weld implement` command
  - Skips post-step review prompt to avoid Claude CLI date serialization bugs
  - Workaround for "RangeError: Invalid time value" errors during review step
  - Useful when Claude CLI stats cache has issues
- Multiple transcript gist support in `weld commit` fallback mode
  - Now uploads separate gists for each session that contributed to staged files
  - Example: implement session + review session = 2 gists attached to commit
  - Each gist labeled with command type (implement, review, etc.)
  - Provides complete context for understanding changes
- Smart error recovery in `weld implement` command
  - When Claude crashes after making file changes, detects modifications and prompts user
  - Allows marking step as complete despite Claude error if work was actually done
  - Prevents losing progress when Claude has internal failures
  - Only prompts if file changes detected; genuine failures still return error

### Changed
- Enhanced `weld plan` prompt with 10 implementation plan rules
  - Monotonic phases, discrete steps, artifact-driven output
  - Explicit dependencies, vertical slices, invariants first
  - Test parallelism, rollback safety, bounded scope, execution ready
  - Rules condensed to minimize context usage while enforcing plan quality
- Optimized `weld implement` prompt to skip redundant test runs
  - When Claude identifies a step as already complete (but not marked), checks git status first
  - If worktree is clean: marks step complete without running tests
  - If worktree is dirty: reviews uncommitted changes and proceeds without re-running tests
  - Significant time savings when resuming after crashes or re-running completed steps

### Fixed
- **Critical**: Plan generation now strictly enforces required Phase → Step format
  - Added explicit format requirements to prompt to prevent conversational output
  - Added validation to reject plans that don't start with "## Phase" or lack steps
  - Fixed issue where Claude would output summaries/questions instead of structured plans
  - Plans now correctly follow docs/reference/plan-format.md specification
- **Critical**: `weld commit` now attaches transcripts from ALL relevant sessions
  - Fallback flow finds all sessions from registry that match staged files
  - Uploads one gist per matching session (e.g., implement + review)
  - Fixes issue where only one transcript was attached when multiple sessions contributed
  - Each transcript gets its own trailer line in commit message

## [0.6.0] - 2026-01-09

### Added
- Interactive review prompt after step completion in `weld implement` command
  - Prompts user to review changes with optional auto-fixing via `weld review --diff [--apply]`
  - Non-blocking: review failures don't stop implement flow
  - Always available (independent of --auto-commit flag)

### Fixed
- Interactive menu cursor position in `weld implement` - now automatically positions on first incomplete step
- Makefile `bin-install` target now forces package rebuild with `--force` flag to pick up source changes
- **Critical**: EOFError handling in auto-commit prompt (now handles non-interactive environments)
- **Critical**: File I/O error handling in review prompt (disk full/permission errors no longer crash)
- **Critical**: Exception handling for review prompt generation
- Directory naming for review artifacts (sanitize step numbers with dots, e.g., "1.2" → "1-2")
- Added model parameter to review Claude invocations (respects configured model)
- Removed redundant git status check in review prompt (performance improvement)
- Config validation with safe defaults for review feature (graceful handling of malformed configs)
- Result validation for empty Claude output in reviews
- Consistent error messages across all non-blocking failures
- Security documentation for `skip_permissions` behavior in review auto-fix mode

## [0.5.0] - 2026-01-09

### Added
- Native transcript generation (replaces external `claude-code-transcripts` binary)
  - Session detection: Automatically finds Claude Code sessions from `~/.claude/projects/`
  - Session tracking: Records file changes during weld commands
  - Transcript rendering: Converts Claude JSONL sessions to markdown with:
    - Secret redaction (API keys, tokens, credentials)
    - Content truncation (tool results, thinking blocks)
    - Size limits (per-message and total)
  - Gist upload: Publishes transcripts to GitHub Gists via `gh` CLI
- Automatic session tracking in `weld implement` command for commit provenance
- Config migration for `[claude.transcripts]` → `[transcripts]` format
- File snapshot timeout protection for large repositories
- Session models: `SessionActivity`, `TrackedSession` in `weld.models`
- Session services: `session_detector`, `session_tracker`, `transcript_renderer`, `gist_uploader`
- `get_sessions_dir()` helper in `weld.core.weld_dir`
- Session-based commit grouping: `weld commit` now groups files by originating Claude session
  - Each session gets its own commit with transcript attached
  - `--no-session-split` flag to disable session-based grouping
- MkDocs documentation site with Material theme
  - Full command reference and configuration docs
  - GitHub Actions workflow for automatic deployment to GitHub Pages
  - Makefile targets: `docs`, `docs-build`, `docs-deploy`, `docs-version`
  - Versioned documentation support via mike
- Codebase exploration guidance in `weld plan` prompts
  - Instructs Claude to explore the codebase structure before planning
  - Requires identification of relevant files and existing patterns
  - Grounds plans in concrete code locations and line numbers
- Documentation clarifying `weld implement` session behavior
  - Each step execution is an independent Claude CLI invocation with fresh context
  - No conversational memory between steps
  - Session tracking is for commit grouping, not conversational context
- `--auto-commit` flag for `weld implement` command
  - Prompts user to commit changes after each step completes successfully
  - Automatically stages all changes (like `weld commit --all`)
  - Creates session-based commits with transcript attachment
  - Non-blocking: commit failures don't stop the implement flow
  - Skips prompt if no changes detected during the step
  - Manual session recording ensures transcripts are included in mid-execution commits

### Changed
- Transcript configuration moved from `[claude.transcripts]` to top-level `[transcripts]`
  - Automatic migration from old config format
  - New `enabled` field to toggle transcript generation
  - Removed `exec` field (no longer needed with native implementation)
- Simplified README.md, moved detailed content to documentation site
- `weld commit` now uses native transcript rendering instead of external binary
- `weld implement` now automatically tracks file changes (no flag required)
- Session-based commits fully functional with implement workflow
- Registry pruning after successful commits to keep registry clean
- Makefile `bump-*` targets now automatically run `uv sync` after version update

### Fixed
- Session tracking gracefully handles missing Claude sessions
- File snapshot performance improved for large repositories (5s timeout)
- Config migration creates backup and safely rolls back on errors

### Removed
- `--edit/-e` flag from `weld commit` (use `git commit --amend` to edit after)

## [0.4.1] - 2026-01-07

### Added
- Configurable `max_output_tokens` setting in `[claude]` config section
  - Default: 128,000 tokens (sufficient for most large document operations)
  - Passed to Claude CLI via `CLAUDE_CODE_MAX_OUTPUT_TOKENS` environment variable
  - Helpful error message displayed when token limit is exceeded, explaining how to fix

## [0.4.0] - 2026-01-07

### Added
- `--focus/-f` option for `weld review` command to focus review on specific topics
  - Works with both document review and code review modes
  - Injects focus area into AI prompts for targeted analysis

## [0.3.1] - 2026-01-07

### Added
- Automated release workflow (`.github/workflows/release.yml`)
  - Tag-triggered GitHub Actions workflow for PyPI and GitHub releases
  - Quality gates (ruff, pyright, pytest) run before publish
  - Version validation between `pyproject.toml` and git tag
  - PyPI Trusted Publishing via OIDC (no API tokens required)
  - Automatic release notes extraction from CHANGELOG.md
  - GitHub Release creation with wheel/sdist artifacts
- Release helper scripts in `scripts/`:
  - `extract_release_notes.py`: Parse CHANGELOG for version section
  - `assert_unreleased_empty.py`: Validate unreleased section is empty before tagging
- PyPI packaging metadata per [packaging.python.org](https://packaging.python.org/en/latest/tutorials/packaging-projects/) guidelines
  - Authors, readme, license-files fields
  - Classifiers for Python versions, license, and topics
  - Project URLs (Homepage, Documentation, Repository, Issues, Changelog)

## [0.3.0] - 2026-01-07

### Added
- Optional `--output` for `weld plan`, `weld research`, and `weld discover` commands
  - Without `--output`, writes to `.weld/<command>/{filename}-{timestamp}.md`
  - Requires weld initialization when using default paths
- `--focus/-f` option for `weld research` to focus analysis on specific areas
- `make release VERSION=x.y.z` target for creating GitHub releases from CHANGELOG

### Fixed
- Claude prompts now passed via stdin instead of `-p` argument to avoid OS "Argument list too long" errors on large prompts
- Claude streaming output now includes newlines in return value between discrete JSON messages, ensuring consistency between displayed output and returned string

## [0.2.0] - 2026-01-07

### Added
- `weld implement` command for interactive plan execution
  - Arrow-key navigable menu for selecting phases/steps
  - Non-interactive mode via `--step` and `--phase` flags for CI/automation
  - Graceful Ctrl+C handling that preserves progress
  - Atomic checkpointing after each step completion
- Plan parser module (`weld.core.plan_parser`) for parsing phased implementation plans
  - `Step`, `Phase`, `Plan`, `ValidationResult` data classes
  - `parse_plan()` and `validate_plan()` functions for structured plan extraction
  - `mark_step_complete()` and `mark_phase_complete()` for atomic progress tracking
  - `get_phase_by_number()` and `get_step_by_number()` helper methods on `Plan`
  - Atomic file writes using temp file + rename pattern
- Code review mode for `weld review` command with `--diff` flag
  - Reviews git diff for bugs, security issues, missing implementations, and test problems
  - `--staged` flag to review only staged changes
  - `--apply` flag to have Claude fix all issues directly in the codebase
  - Prompt templates optimized for actionable code review findings
- `--no-split` flag for `weld commit` to disable automatic commit splitting
- `--edit/-e` flag for `weld commit` to review/edit generated commit message in `$EDITOR`
- `--timeout/-t` option for `weld review` to override Claude timeout
- `[claude].timeout` configuration option in `.weld/config.toml` (default: 1800s)
- `simple-term-menu` dependency for interactive terminal menus
- `get_staged_files()`, `unstage_all()`, `stage_files()` git helpers for commit splitting
- `is_file_staged()` helper in git service for checking if specific file is staged
- CHANGELOG duplicate detection to prevent re-adding same entries on retry
- Debug output showing Claude response when commit message parsing fails
- `core/history.py`: Lightweight JSONL-based command history tracking
  - `HistoryEntry` model with timestamp, input, and output paths
  - `log_command()`, `read_history()`, `prune_history()` functions
  - Per-command history files in `.weld/<command>/history.jsonl`
- `core/weld_dir.py`: Simple `.weld` directory path resolution
- Proper error handling in commit command for git failures
- Weld initialization checks in plan, research, and discover commands
- Comprehensive test coverage for `weld review` and `weld commit` commands
  - 33 CLI tests for doc_review command covering dry-run, prompt-only, and full execution modes
  - 33 tests for commit command covering parsing, changelog updates, and CLI options
- Comprehensive test suites for plan parser and implement command
  - `tests/test_plan_parser.py`: 26 tests for parsing, validation, and completion marking
  - `tests/test_implement.py`: 18 tests for CLI, interactive mode, and error handling

### Changed
- **Major simplification**: Removed run-centric architecture in favor of lightweight prompt-based workflow
  - Weld now focuses on generating prompts for Claude Code rather than managing runs/steps
  - Commands generate prompts that users paste into Claude Code for execution
  - History tracking via simple JSONL files per command type
- Simplified CLI to 8 focused commands: `init`, `commit`, `plan`, `research`, `discover`, `interview`, `review`, `doctor`
- `weld commit` now automatically splits changes into logical commits
  - Analyzes diff and groups files by logical change (typo fixes, version updates, docs, etc.)
  - Creates separate commits for each group in logical order
  - Transcript gist attached to final commit only
  - Use `--no-split` to force single commit behavior
- `weld plan` now generates plans with hierarchical Phase -> Step structure
  - Plans divided into discrete incremental phases (`## Phase N: <Title>`)
  - Each phase contains discrete steps (`### Step N: <Title>`)
  - Step numbers restart at 1 within each phase
  - Added Phase Validation section for verifying entire phases
- Claude service rewritten with proper `select()`-based streaming and timeout handling
- Claude streaming output now shows colored `claude>` prefix for each line
- Default Claude timeout increased from 600s to 1800s (30 minutes) for apply operations
- `--apply` mode now automatically passes `--dangerously-skip-permissions` to Claude for write access
- Transcript timeout increased from 60s to 120s for larger transcripts
- Commit command now uses distinct exit codes: 21 (Claude error), 22 (git error), 23 (parse error), 24 (editor error)
- History logging now stores commit message subject instead of diff snippet
- CHANGELOG staging now preserves user's partial staging (warns if already staged)
- Reduced models to just `DiscoverMeta`, `Issue`, and `Issues`

### Removed
- Run-centric workflow and all associated infrastructure:
  - Commands: `run`, `step`, `status`, `next`, `list`
  - Core modules: `run_manager`, `step_processor`, `loop`, `review_engine`, `plan_parser`, `commit_handler`, `lock_manager`, `artifact_versioning`, `research_processor`
  - Models: `Meta`, `Step`, `Status`, `Lock`, `Timing`, `VersionInfo`, `StaleOverride`, `CommandEvent`, `CategoryResult`, `ChecksSummary`
  - Services: `codex`, `checks`, `diff`, `streaming`
- Plan subcommands (`import`, `export`, `show`, `prompt`, `review`)
- Research subcommands (`prompt`, `import`, `show`)
- Step subcommands (`select`, `loop`, `review`, `skip`)
- Run subcommands (`start`, `abandon`, `continue`)
- Multi-category checks configuration
- Run locking and heartbeat tracking
- Artifact versioning with history snapshots
- Codex CLI integration (now Claude-only)
- TaskType enum and per-task model selection

### Fixed
- Claude streaming now properly handles timeouts using `select()` instead of blocking reads
- Fixed CHANGELOG update potentially overwriting user's carefully staged hunks
- Fixed silent failure when Claude returns unparseable response (now shows response for debugging)
- Fixed streaming output prefix printing spurious `claude>` on empty lines
- Commit command catches `GitError` and reports failures gracefully
- Discover command no longer silently swallows exceptions
- History reading handles empty files and whitespace-only content
- Commands verify weld is initialized before accessing `.weld` directory

## [0.1.0] - 2026-01-04

Initial release of the weld CLI, a human-in-the-loop coding harness with transcript provenance.

### Added

#### Core Features
- Human-in-the-loop coding workflow: plan, implement, review, iterate, commit
- Plan generation and parsing with strict and lenient format support
- Step-by-step implementation with AI-powered code review loop
- Transcript provenance tracking via git commit trailers
- Configurable checks integration (tests, linting, etc.)

#### Data Models (Pydantic)
- `Meta` model for run metadata and spec references
- `Step` model for parsed plan steps with acceptance criteria
- `Issue` and `Issues` models for structured review results
- `Status` model for iteration pass/fail tracking

#### CLI Commands
- `weld init` - Initialize weld in a git repository
- `weld run` - Create a new run from a spec file
- `weld list` - List all runs in the repository
- `weld plan import/export/show` - Manage AI-generated plans
- `weld step select/loop/review` - Execute implementation workflow
- `weld commit` - Create commits with transcript trailers

#### Enterprise CLI Features
- `--version` / `-V` flag for version display
- `--verbose` / `-v` flag for increased output (supports -vv)
- `--quiet` / `-q` flag to suppress non-error output
- `--json` flag for machine-readable output
- `--no-color` flag to disable colored output
- `python -m weld` support for module execution

#### Multi-Provider AI Support
- Claude CLI integration as primary AI provider
- Codex CLI integration for code review
- Per-task model selection configuration
- Provider-agnostic artifact file naming

#### Architecture
- Layered structure: `cli.py` -> `commands/` -> `core/` -> `services/`
- Services package for external integrations (git, codex, claude, transcripts)
- Core package for business logic (plan parser, step processor, loop, review engine)
- Models package for Pydantic data models

#### Developer Experience
- Makefile with common development tasks (`make setup`, `make test`, `make check`)
- GitHub Actions CI workflow for lint, test, and security checks
- Pre-commit hooks for ruff, pyright, and detect-secrets
- Comprehensive test suite with 70%+ coverage target
- Property-based testing with Hypothesis

#### Documentation
- Comprehensive README with quickstart guide
- CLAUDE.md with architecture and commands reference
- Google-style docstrings on all public APIs
- Module-level documentation throughout

### Security
- Input validation for file paths with repository boundary checks
- Run ID format validation
- Removed `shell=True` from all subprocess calls (uses `shlex.split`)
- Consistent timeout enforcement on all subprocess operations:
  - Git operations: 30 seconds
  - AI operations (Codex, Claude): 10 minutes
  - Check commands: 5 minutes
  - Transcript generation: 60 seconds
  - Tool availability checks: 10 seconds

[Unreleased]: https://github.com/ametel01/weld-cli/compare/v0.11.1...HEAD
[0.11.1]: https://github.com/ametel01/weld-cli/compare/v0.11.0...v0.11.1
[0.11.0]: https://github.com/ametel01/weld-cli/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/ametel01/weld-cli/compare/v0.9.1...v0.10.0
[0.9.1]: https://github.com/ametel01/weld-cli/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/ametel01/weld-cli/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/ametel01/weld-cli/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/ametel01/weld-cli/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/ametel01/weld-cli/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/ametel01/weld-cli/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/ametel01/weld-cli/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/ametel01/weld-cli/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/ametel01/weld-cli/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/ametel01/weld-cli/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/ametel01/weld-cli/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ametel01/weld-cli/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ametel01/weld-cli/releases/tag/v0.1.0
