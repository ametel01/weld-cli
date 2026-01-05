# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New TaskType values: `DISCOVER`, `INTERVIEW`, `RESEARCH`, `RESEARCH_REVIEW` for brownfield and research workflows
- TaskModelsConfig fields for new workflow phases with sensible defaults (generative → claude, review → codex)
- Multi-category checks configuration with separate `lint`, `test`, `typecheck` commands
- Run locking to prevent concurrent modifications to the same weld project
- PID-based lock files with stale lock detection and automatic cleanup
- Heartbeat updates during long-running operations to prevent false stale detection
- Configurable execution order for check categories
- Per-category output files in `checks/` subdirectory
- `checks.summary.json` with aggregated results and first-failure tracking
- `CategoryResult` and `ChecksSummary` Pydantic models for structured check results

### Changed
- Checks now run with fail-fast in iteration loop, full run for review context
- Implementation prompt displays all configured check commands
- Status model enriched with `checks_summary` field

### Deprecated
- Single-command `checks.command` field (use category fields instead)
- Flat `checks_exit_code` in Status (use `checks_summary.get_exit_code()`)

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

[Unreleased]: https://github.com/user/weld-cli/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/user/weld-cli/releases/tag/v0.1.0
