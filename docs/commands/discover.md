# weld discover

Analyze codebase and generate architecture documentation.

## Usage

```bash
weld discover [OPTIONS]
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--output` | `-o` | Path to write output (default: `.weld/discover/{timestamp}.md`) |
| `--focus` | `-f` | Specific areas to focus on |
| `--prompt-only` | | Output prompt without running Claude |
| `--quiet` | `-q` | Suppress streaming output |

## Description

Generates a prompt that guides Claude to analyze your codebase and document:

- High-level architecture
- Directory structure
- Key files and entry points
- Testing patterns
- Security considerations

## Examples

### Discover entire codebase

```bash
weld discover
```

### Focus on specific area

```bash
weld discover --focus "authentication system"
```

### Write to specific location

```bash
weld discover -o docs/architecture.md
```

### Preview prompt only

```bash
weld discover --prompt-only
```

## Input Validation

Before starting the (potentially expensive) Claude operation, weld validates inputs upfront:

- **Output path**: If `--output` is specified, validates the path is writable and is a file (not a directory)

When validation fails, you'll see a clear error message with an actionable hint:

```
Error: docs/ is a directory, expected a file
Hint: Provide a file path: --output /path/output.md
```

This prevents wasted API tokens from invalid inputs.

## Subcommands

### weld discover show

Show a previously generated discover prompt.

```bash
weld discover show
```

## See Also

- [Workflow](../workflow.md) - How discover fits in the workflow
- [interview](interview.md) - Refine specifications after discovery
