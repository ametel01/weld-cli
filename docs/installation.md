# Installation

## Prerequisites

| Tool | Required | Description |
|------|----------|-------------|
| **Python 3.11+** | Yes | Runtime environment |
| **uv** or **pipx** | Yes | Global CLI installation |
| **git** | Yes | Version control |
| **gh** | Yes | GitHub CLI (auth via `gh auth login` for transcript uploads) |
| **claude** | Optional | Claude Code CLI (AI provider) |

## Install from PyPI (Recommended)

Install weld as a global CLI tool:

```bash
# Using uv (recommended)
uv tool install weld-cli

# Or using pipx
pipx install weld-cli

# Verify installation
weld --help

# Upgrade to latest version
uv tool upgrade weld-cli    # or: pipx upgrade weld-cli
```

Now `weld` is available system-wide. Use it in any project:

```bash
cd /path/to/your-project
weld init
weld doctor
```

## Verify Toolchain

```bash
# Check all required dependencies
weld doctor
```

This validates:
- **Required**: `git`, `gh`
- **Optional**: `claude`, `codex`

Note: `weld doctor` checks if tools are in PATH. For `gh`, run `gh auth login` separately to enable transcript uploads.

## Install from Source

For contributing to weld or running the latest unreleased code:

```bash
git clone https://github.com/ametel01/weld-cli.git && cd weld-cli

# Option 1: Install globally from source
uv tool install .

# Option 2: Development setup with editable install
make setup
eval $(make venv-eval)
weld --help
```

## Python Dependencies

These are installed automatically with weld:

| Package | Purpose |
|---------|---------|
| typer | CLI framework |
| rich | Terminal formatting |
| pydantic | Data validation |
| simple-term-menu | Interactive menus for `weld implement` |

## Development Dependencies

For contributing to weld:

- **make** - Build automation
- **uv** - Package manager

See [Development Guide](development/index.md) for setup instructions.
