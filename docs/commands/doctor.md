# weld doctor

Check environment and dependencies.

## Usage

```bash
weld doctor
```

## Description

Validates that all required and optional tools are available and properly configured.

### Required Tools

| Tool | Purpose |
|------|---------|
| `git` | Version control |
| `gh` | GitHub CLI (run `gh auth login` separately for transcript uploads) |

### Optional Tools

| Tool | Purpose |
|------|---------|
| `codex` | Codex CLI for AI operations |
| `claude` | Claude Code CLI for AI operations |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All required dependencies available |
| 2 | Required dependencies missing |

## Examples

### Check environment

```bash
weld doctor
```

### After installation

```bash
weld init && weld doctor
```

## See Also

- [Installation](../installation.md) - Install missing dependencies
- [Troubleshooting](../troubleshooting.md) - Fix common issues
