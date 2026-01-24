# prompt

Manage prompt customizations configured in `.weld/config.toml`.

## Usage

```bash
weld prompt              # List all prompt types (same as 'list')
weld prompt list         # List all prompt types with customization status
weld prompt show <type>  # Show customization for a specific task type
weld prompt export       # Export customizations as TOML/JSON
```

## Subcommands

### list

List all available prompt types with their descriptions and customization status.

```bash
weld prompt list
weld prompt list --json  # JSON output for automation
```

**Output columns:**

- **Type**: Task type identifier (e.g., `discover`, `research`)
- **Description**: What the task does
- **Customized**: Whether prefix/suffix/default_focus is configured

### show

Display the customization settings for a specific task type.

```bash
weld prompt show discover           # Show customization details
weld prompt show research --raw     # Output raw template (pipe-friendly)
weld prompt show plan_generation --focus "API"  # Preview with focus value
```

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--raw` | `-r` | Output raw prompt template without Rich formatting |
| `--focus` | `-f` | Focus value to apply to template preview |

**Available task types:**

- `discover` - Brownfield codebase discovery and analysis
- `interview` - Interactive specification refinement
- `research` - Research prompts for gathering context
- `research_review` - Review of research outputs
- `plan_generation` - Implementation plan generation
- `plan_review` - Review of generated plans
- `implementation` - Code implementation phase
- `implementation_review` - Review of implemented code
- `fix_generation` - Generate fixes for review feedback
- `doc_review` - Document review and analysis
- `code_review` - Code review and quality assessment
- `commit` - Commit message generation

### export

Export prompt templates or customizations.

```bash
# Export as markdown files
weld prompt export ./prompts --raw

# Export config as TOML (stdout)
weld prompt export --format toml

# Export config as JSON to file
weld prompt export -o prompts.json --format json
```

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--raw` | `-r` | Export raw prompt templates as markdown files |
| `--format` | `-f` | Export format: `toml` or `json` (default: `toml`) |
| `--output` | `-o` | Output file path (stdout if not specified) |

**With `--raw`:**

- Creates one markdown file per task type (e.g., `discover.md`, `research.md`)
- Each file includes the base template with any configured customizations
- Useful for reviewing or editing prompt templates externally

**Without `--raw`:**

- Exports only the customization settings from config
- Outputs to stdout or specified file
- Useful for backing up or sharing prompt configurations

## Examples

### View all prompt types

```bash
$ weld prompt list
Available Prompt Types

┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Type                  ┃ Description                             ┃ Customized ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ discover              │ Brownfield codebase discovery           │     ✓      │
│ research              │ Research prompts for gathering context  │     -      │
│ plan_generation       │ Implementation plan generation          │     ✓      │
...
```

### Check a specific task's customization

```bash
$ weld prompt show discover
Prompt Customization: discover

Global:
  prefix: This is a Python project using FastAPI.
  suffix: (none)

Task (discover):
  prefix: Focus on the API layer.
  suffix: (none)
  default_focus: architecture
```

### Export templates for review

```bash
$ weld prompt export ./my-prompts --raw
Exported 12 prompt templates to ./my-prompts

$ ls ./my-prompts/
commit.md          discover.md        implementation.md  ...
```

### Backup customizations

```bash
$ weld prompt export --format toml > prompts-backup.toml
```

## Configuration

Prompt customizations are configured in `.weld/config.toml`:

```toml
[prompts]
global_prefix = "This is a Python 3.12 project."
global_suffix = "Always include type hints."

[prompts.discover]
prefix = "Focus on the data model."
default_focus = "architecture"

[prompts.research]
prefix = "Consider security implications."
suffix = "Include risk assessment."
default_focus = "security"
```

See [Configuration](../configuration.md#prompts) for full details.

## How Customizations Apply

When a prompt is generated for a task, customizations are applied in layers:

1. **Global prefix** is prepended (if configured)
2. **Task-specific prefix** is prepended (if configured)
3. **Base prompt** for the task
4. **Task-specific suffix** is appended (if configured)
5. **Global suffix** is appended (if configured)

The `default_focus` provides a fallback value for the `--focus` flag when not specified on the command line.

## Exit Codes

| Code | Description |
|------|-------------|
| 0 | Success |
| 1 | Configuration error or invalid task type |
| 3 | Not a git repository |

## See Also

- [Configuration - Prompts](../configuration.md#prompts) - Prompt configuration reference
- [discover](discover.md) - Uses discover prompt customization
- [research](research.md) - Uses research prompt customization
- [plan](plan.md) - Uses plan_generation prompt customization
