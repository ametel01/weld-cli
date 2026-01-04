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
```

## Architecture

Weld is a human-in-the-loop coding harness that orchestrates AI-assisted development through: plan → implement → review → iterate → commit with transcript provenance.

### Layered Structure

```
src/weld/
├── cli.py              # Typer entry point, global options
├── commands/           # CLI command handlers (thin layer, delegates to core/)
├── core/               # Business logic
│   ├── run_manager.py  # Run lifecycle (create, load, list runs)
│   ├── plan_parser.py  # Parse strict/lenient plan formats
│   ├── step_processor.py # Step extraction and prompt generation
│   ├── loop.py         # Implement-review-fix iteration loop
│   ├── review_engine.py # AI review orchestration
│   └── commit_handler.py # Commit with transcript trailers
├── services/           # External integrations (git, codex, claude, transcripts)
└── models/             # Pydantic data models (Meta, Step, Issues, Status)
```

### Key Design Patterns

- **Commands delegate to core**: `commands/*.py` handle CLI parsing, then call `core/*.py` for logic
- **Services wrap external CLIs**: All subprocess calls go through `services/` (never `shell=True`)
- **Pydantic models for JSON contracts**: All run artifacts use models for validation
- **Run artifacts stored in `.weld/runs/<run_id>/`**: Each run is a self-contained directory

### Data Flow

1. `weld run --spec` → creates run directory, generates plan prompt
2. `weld plan import` → imports AI plan, parses steps
3. `weld step loop` → iterates: snapshot diff → AI review → fix prompt until pass
4. `weld commit` → creates commit with transcript gist trailer

## Git Commits

- Never mention Claude Code in commit messages
- Never include the generated footer or Co-Authored-By trailer
- Use imperative mood ("Add feature" not "Added feature")
- Keep commits small and focused
- Before committing update CHANGELOG.md based on the commit messages

## Code Quality

- Never bypass linting with exceptions unless explicitly requested
- Line length: 100 characters (configured in pyproject.toml)
- Type hints required; pyright in standard mode
- Test markers: `@pytest.mark.unit`, `@pytest.mark.cli`, `@pytest.mark.slow`
