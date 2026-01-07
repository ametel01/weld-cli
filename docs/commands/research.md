# weld research

Research a specification before planning.

## Usage

```bash
weld research <input> [OPTIONS]
```

## Arguments

| Argument | Description |
|----------|-------------|
| `input` | Path to the specification file |

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--output` | `-o` | Path to write research (default: `.weld/research/`) |
| `--focus` | `-f` | Specific areas to focus on |
| `--quiet` | `-q` | Suppress streaming output |

## Description

Generates a research prompt and runs Claude to analyze:

- Architecture and existing patterns
- Dependencies and integration points
- Risks and open questions

## Examples

### Research a specification

```bash
weld research specs/feature.md
```

### Write to specific location

```bash
weld research specs/feature.md -o research.md
```

### Focus on specific concerns

```bash
weld research specs/feature.md --focus "security concerns"
```

### Suppress streaming output

```bash
weld research specs/feature.md -o research.md --quiet
```

## Output

Research output is written to `.weld/research/` by default with a timestamped filename.

## See Also

- [Workflow](../workflow.md) - How research fits in the workflow
- [plan](plan.md) - Generate a plan after research
