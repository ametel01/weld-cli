# Commands Reference

## Global Options

All commands support these global options:

| Option | Short | Description |
|--------|-------|-------------|
| `--version` | `-V` | Show version and exit |
| `--verbose` | `-v` | Increase verbosity (`-v` for verbose, `-vv` for debug) |
| `--quiet` | `-q` | Suppress non-error output |
| `--json` | | Output in JSON format for automation |
| `--no-color` | | Disable colored output |
| `--dry-run` | | Preview effects without applying changes |
| `--debug` | | Enable file-based debug logging to `.weld/debug.log` |

## Commands

| Command | Description |
|---------|-------------|
| [init](init.md) | Initialize weld in a git repository |
| [doctor](doctor.md) | Check environment and dependencies |
| [discover](discover.md) | Analyze codebase architecture |
| [interview](interview.md) | Refine specifications through Q&A |
| [research](research.md) | Research a specification |
| [plan](plan.md) | Generate an implementation plan |
| [implement](implement.md) | Execute a plan interactively |
| [review](review.md) | Review documents or code changes |
| [commit](commit.md) | Commit with transcript provenance |

## Command Categories

### Setup Commands

- **[init](init.md)** - Initialize weld in your project
- **[doctor](doctor.md)** - Verify your toolchain

### Discovery Commands

- **[discover](discover.md)** - Analyze existing codebase
- **[interview](interview.md)** - Refine specifications

### Planning Commands

- **[research](research.md)** - Research implementation approach
- **[plan](plan.md)** - Generate step-by-step plan

### Execution Commands

- **[implement](implement.md)** - Execute plan steps
- **[review](review.md)** - Validate documents and code
- **[commit](commit.md)** - Create commits with provenance

## See Also

- [Exit Codes](../reference/exit-codes.md) - Exit code reference
- [Configuration](../configuration.md) - Configure weld behavior
