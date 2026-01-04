## Enterprise-grade best practices for a `uv`-managed Python CLI tool

### Project layout (CLI-first, testable, packageable)

Use `src/` layout and keep CLI thin.

```
mycli/
  pyproject.toml
  uv.lock
  src/mycli/
    __init__.py
    __main__.py
    cli.py
    commands/
      __init__.py
      foo.py
    core/
      __init__.py
      logic.py
    services/
      __init__.py
      fs.py
      net.py
  tests/
    test_cli.py
    test_logic.py
  README.md
```

Principles

* **`cli.py`**: argument parsing + command dispatch only.
* **`core/`**: pure logic, easy unit tests.
* **`services/`**: side effects (filesystem/network/subprocess), injectable/mocked.

---

## `uv` workflow standard (local + CI)

### Commands developers run

* Install/sync: `uv sync`
* Run CLI: `uv run mycli ...`
* Run tests: `uv run pytest`
* Lint: `uv run ruff check .`
* Format: `uv run ruff format .` (or `uv run black .`)
* Typecheck: `uv run pyright`

### CI should run (no autofix)

* `uv sync --frozen`
* `uv run ruff format --check .`
* `uv run ruff check .`
* `uv run pyright`
* `uv run pytest -q --maxfail=1`
* `uv run pip-audit` (or `uv run pip-audit -r <exported requirements>` if needed)

---

## `pyproject.toml` baseline (uv + CLI + quality gates)

```toml
[project]
name = "mycli"
version = "0.1.0"
description = "My CLI tool"
requires-python = ">=3.11"
dependencies = [
  "typer>=0.12",
  "rich>=13.7",
]

[project.scripts]
mycli = "mycli.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
target-version = "py311"
line-length = 100
src = ["src"]

[tool.ruff.lint]
select = ["E","F","I","UP","B","SIM","C4","RUF"]
ignore = []

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.pyright]
typeCheckingMode = "standard"
pythonVersion = "3.11"
include = ["src"]
```

Notes

* `project.scripts` makes a proper entry point (`mycli`).
* `hatchling` is a clean default build backend for CLIs.
* Ruff rule-set chosen for CLI repos: correctness + modernization + import hygiene.

---

## CLI implementation best practices (enterprise-grade)

### Use a real CLI framework

* Prefer **Typer** (excellent UX, type-hints map well to args/options).
* Alternate: Click (mature), argparse (stdlib, minimal deps).

### Make failures predictable

* Exit codes: `0` success, `1` generic error, `2` usage error, etc.
* Print user-facing errors to **stderr**, and keep them concise.
* Provide `--json` for machine-readable output if automation matters.

### Logging strategy

* Default: quiet user output; add `--verbose/-v` for logs.
* For CI / automation: `--log-level` and `--no-color`.
* If you emit logs, separate them from primary output (stderr vs stdout).

### Configuration

* Support precedence:

  1. CLI flags
  2. environment variables
  3. config file (e.g., `~/.config/mycli/config.toml`)
  4. defaults
* Use `platformdirs` to locate config directories.

---

## Testing strategy for a CLI tool

### Unit tests

* Pure logic in `core/` with straightforward tests.

### CLI tests

* For Typer: `typer.testing.CliRunner()`
* Assert:

  * exit code
  * stdout/stderr
  * behavior under invalid args
  * behavior with env vars / config

### Integration tests (optional but common)

* Use `tmp_path` for filesystem scenarios.
* Mock network/subprocess calls unless you explicitly test them behind a marker.

---

## Security + supply chain for CLIs

* Dependency scanning: `pip-audit` in CI.
* Secret scanning: `detect-secrets` or `gitleaks` pre-commit + CI.
* If invoking subprocesses:

  * avoid `shell=True`
  * sanitize args
  * timeouts everywhere
* If handling files:

  * avoid unsafe path joins (validate inputs; use `pathlib`)

---

## Pre-commit (works perfectly with `uv run`)

`.pre-commit-config.yaml` recommended hooks:

* ruff (lint)
* ruff (format)
* pyright (optional; can be slow but doable)
* detect-secrets

Run hooks via:

* `uv run pre-commit install`
* `uv run pre-commit run -a`

---

## Release and packaging (CLI distribution)

* Build: `uv run python -m build`
* Publish: `uv run twine upload dist/*`
* Add `--version` and `mycli version` command (handy for support).
* Consider shipping a single-file binary (optional):

  * `pyinstaller` / `shiv` / `pex` depending on target environment.

---

## CI (GitHub Actions skeleton for `uv`)

Core pattern:

* checkout
* install uv
* `uv sync --frozen`
* run quality gates listed above

---

If you want, I can output a complete ready-to-drop-in repo scaffold: `pyproject.toml`, `ruff/pyright` settings, `pre-commit` config, and a GitHub Actions workflow using `uv sync --frozen`, plus a minimal Typer-based CLI with one command and tests.
