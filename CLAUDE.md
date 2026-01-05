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

Weld is a prompt-generation tool for AI-assisted development. It creates structured prompts for: research → plan → review → commit with transcript provenance.

### Layered Structure

```
src/weld/
├── cli.py              # Typer entry point, global options
├── commands/           # CLI command handlers (thin layer)
│   ├── init.py         # weld init
│   ├── plan.py         # weld plan
│   ├── research.py     # weld research
│   ├── discover.py     # weld discover
│   ├── interview.py    # weld interview
│   ├── doc_review.py   # weld review
│   ├── commit.py       # weld commit
│   └── doctor.py       # weld doctor
├── core/               # Business logic
│   ├── history.py      # JSONL command history tracking
│   ├── weld_dir.py     # .weld directory utilities
│   ├── discover_engine.py    # Codebase discovery prompts
│   ├── interview_engine.py   # Specification refinement prompts
│   └── doc_review_engine.py  # Document review prompts
├── services/           # External integrations (git, claude, transcripts)
└── models/             # Pydantic data models (DiscoverMeta, Issue, Issues)
```

### Key Design Patterns

- **Commands delegate to core**: `commands/*.py` handle CLI parsing, then call `core/*.py` for logic
- **Services wrap external CLIs**: All subprocess calls go through `services/` (never `shell=True`)
- **JSONL history**: Each command logs to `.weld/<command>/history.jsonl`

### Data Flow

1. `weld research spec.md -o research.md` → generates research prompt, runs Claude
2. `weld plan spec.md -o plan.md` → generates plan prompt, runs Claude
3. `weld review plan.md --apply` → validates against codebase, applies corrections
4. `weld commit -m "message"` → creates commit with transcript gist trailer

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
