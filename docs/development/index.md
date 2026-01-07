# Developer Guide

This guide covers contributing to weld and understanding its architecture.

## Getting Started

### Development Setup

```bash
git clone https://github.com/ametel01/weld-cli.git && cd weld-cli

# Full setup (dependencies + pre-commit hooks)
make setup

# Activate virtual environment
eval $(make venv-eval)

# Verify installation
weld --help
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

### Running Single Tests

```bash
# Run single test file
.venv/bin/pytest tests/test_config.py -v

# Run single test function
.venv/bin/pytest tests/test_config.py::test_function_name -v
```

## Architecture

See [Architecture](architecture.md) for detailed documentation.

### Quick Overview

Weld follows a simple layered architecture:

```
src/weld/
├── cli.py              # Typer app entry point, global options
├── commands/           # CLI command modules (thin layer)
├── core/               # Business logic
├── services/           # External integrations (git, claude, transcripts)
└── models/             # Pydantic data models
```

### Key Design Patterns

- **Commands delegate to core**: `commands/*.py` handle CLI parsing, then call `core/*.py` for logic
- **Services wrap external CLIs**: All subprocess calls go through `services/` (never `shell=True`)
- **JSONL history**: Each command logs to `.weld/<command>/history.jsonl`

## Code Quality Standards

- **Line length**: 100 characters (configured in pyproject.toml)
- **Type hints**: Required; pyright in standard mode
- **Test markers**: `@pytest.mark.unit`, `@pytest.mark.cli`, `@pytest.mark.slow`

## Git Commit Guidelines

- Use imperative mood ("Add feature" not "Added feature")
- Keep commits small and focused
- Update CHANGELOG.md based on commit messages

## See Also

- [Architecture](architecture.md) - Detailed architecture documentation
- [Contributing](contributing.md) - Contribution guidelines
