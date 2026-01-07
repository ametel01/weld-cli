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

## Subcommands

### weld discover show

Show a previously generated discover prompt.

```bash
weld discover show
```

## See Also

- [Workflow](../workflow.md) - How discover fits in the workflow
- [interview](interview.md) - Refine specifications after discovery
