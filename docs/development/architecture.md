# Architecture

Weld follows a simple layered architecture with clear separation of concerns.

## Directory Structure

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
│   ├── implement.py    # weld implement
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
│   ├── plan_parser.py  # Plan parsing and completion tracking
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

## Project Layout

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

## Design Patterns

### Commands Delegate to Core

`commands/*.py` files are thin wrappers that:
1. Parse CLI arguments
2. Validate inputs
3. Call `core/*.py` for business logic
4. Format output

### Services Wrap External CLIs

All subprocess calls go through `services/`:
- Never use `shell=True`
- Proper error handling
- Timeout support
- Logging

### JSONL History

Each command logs to `.weld/<command>/history.jsonl`:
- Provides audit trail
- Enables debugging
- Supports replay

## Data Models

### DiscoverMeta

Metadata for discover artifacts:

```python
class DiscoverMeta(BaseModel):
    discover_id: str
    created_at: datetime
    focus: list[str]
```

### Issues

Review result from AI provider:

```python
class Issue(BaseModel):
    severity: Literal["blocker", "major", "minor"]
    file: str
    hint: str

class Issues(BaseModel):
    pass_: bool = Field(alias="pass")
    issues: list[Issue]
```

## See Also

- [Developer Guide](index.md) - Getting started with development
- [Contributing](contributing.md) - Contribution guidelines
