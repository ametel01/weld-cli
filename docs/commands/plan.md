# weld plan

Generate an implementation plan from a specification.

## Usage

```bash
weld plan <input> [OPTIONS]
```

## Arguments

| Argument | Description |
|----------|-------------|
| `input` | Path to the specification file |

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--output` | `-o` | Path to write the plan (default: `.weld/plan/`) |
| `--quiet` | `-q` | Suppress streaming output |

## Description

The command:

1. Reads the specification file
2. Generates a planning prompt
3. Runs Claude to create the plan
4. Writes the result to the output file

## Examples

### Generate a plan

```bash
weld plan specs/feature.md
```

### Write to specific location

```bash
weld plan specs/feature.md -o plan.md
```

### Suppress streaming output

```bash
weld plan specs/feature.md -o plan.md --quiet
```

## Output

Plans are written to `.weld/plan/` by default with a timestamped filename.

## Input Validation

Before starting the (potentially expensive) Claude operation, weld validates inputs upfront:

- **File existence**: Verifies the input file exists
- **File type**: Ensures the path points to a file, not a directory
- **Output path**: If `--output` is specified, validates the path is writable

When validation fails, you'll see a clear error message with an actionable hint:

```
Error: specs/feature is a directory, expected a file
Hint: Provide a valid specification file path
```

This prevents wasted API tokens from invalid inputs.

## See Also

- [Plan Format](../reference/plan-format.md) - How plans are structured
- [implement](implement.md) - Execute the generated plan
- [review](review.md) - Validate the plan before implementing
