## Best practices spec: OSS `uv` package releases via GitHub tag → CI → GitHub Release (+ PyPI)

### Goals

* Release is **triggered by pushing a git tag** `vX.Y.Z`.
* CI **creates a GitHub Release** and **publishes to PyPI**.
* GitHub Release notes are **pulled automatically from `CHANGELOG.md`**.
* Release is **reproducible** and **fails early** on versioning/changelog mistakes.
* Prefer **PyPI Trusted Publishing (OIDC)** over long-lived API tokens.

---

## Repository requirements

### 1) Version source of truth

* `pyproject.toml` contains `project.version = "X.Y.Z"`.
* The git tag is `vX.Y.Z`.
* CI must assert: `tag_version == pyproject_version`.

### 2) Changelog format (Keep a Changelog compatible)

`CHANGELOG.md` must have:

* An `## [Unreleased]` section at the top.
* Released sections like: `## [0.1.0] - 2026-01-04`
* Content under headings (`###`, `####`, etc.) is allowed.

Example:

```md
## [Unreleased]
### Added
- ...

## [0.1.0] - 2026-01-04
Initial release...
```

---

## Release process (human + automation)

### Human steps (per release)

1. Move entries from `## [Unreleased]` into a new version section `## [X.Y.Z] - YYYY-MM-DD`.
2. Ensure `pyproject.toml` version is set to `X.Y.Z`.
3. Commit to `main`.
4. Create annotated tag: `git tag -a vX.Y.Z -m "vX.Y.Z"`.
5. Push tag: `git push origin vX.Y.Z`.

### CI responsibilities (on tag push)

1. Checkout with full history.
2. Install `uv`, sync dependencies with lockfile (`--frozen`).
3. Run quality gates (format, lint, typecheck, tests).
4. Extract version from tag.
5. Verify `pyproject.toml` version matches tag.
6. Verify `CHANGELOG.md`:

   * `[X.Y.Z]` section exists.
   * `## [Unreleased]` is **empty** (recommended gate).
7. Extract release notes from the `[X.Y.Z]` section and write `RELEASE_NOTES.md`.
8. Build sdist + wheel once.
9. Publish to PyPI (Trusted Publishing preferred).
10. Create GitHub Release using extracted notes and attach artifacts.

---

## Changelog extraction spec (tailored to your structure)

### A) Extract release notes for version `X.Y.Z`

Rules:

* Find section header matching `^## \[X.Y.Z\]` (date suffix optional).
* Capture everything until the next `^## \[` section header or EOF.
* Exclude the header line itself.
* Preserve all markdown below (including nested headings).

Reference implementation (`scripts/extract_release_notes.py`):

```python
import re, sys, pathlib

version = sys.argv[1]
text = pathlib.Path("CHANGELOG.md").read_text(encoding="utf-8")

pattern = rf"""
^##\s+\[{re.escape(version)}\][^\n]*\n
(.*?)
(?=^##\s+\[|\Z)
"""

m = re.search(pattern, text, re.S | re.M | re.X)
if not m:
    raise SystemExit(f"CHANGELOG.md missing section for [{version}]")

notes = m.group(1).strip()
pathlib.Path("RELEASE_NOTES.md").write_text(notes + "\n", encoding="utf-8")
```

### B) Enforce “Unreleased is empty” on tag builds (recommended)

Rule:

* Extract the body of `## [Unreleased]`.
* If it contains non-whitespace content, fail the release.

Reference implementation (`scripts/assert_unreleased_empty.py`):

```python
import re, pathlib

text = pathlib.Path("CHANGELOG.md").read_text(encoding="utf-8")
m = re.search(r"^##\s+\[Unreleased\]\n(.*?)(?=^##\s+\[|\Z)", text, re.S | re.M)

if m and m.group(1).strip():
    raise SystemExit("Unreleased section is not empty — move entries into the release section before tagging.")
```

Policy note:

* This is a “hard gate” that prevents accidental partial releases.
* If you want a softer policy, change it to warn-only (not recommended for clean OSS releases).

---

## GitHub Actions workflow (tag push trigger)

Create: `.github/workflows/release.yml`

```yaml
name: release

on:
  push:
    tags:
      - "v*"

permissions:
  contents: write
  id-token: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Sync deps (locked)
        run: uv sync --frozen

      - name: Quality gates
        run: |
          uv run ruff format --check .
          uv run ruff check .
          uv run pyright
          uv run pytest -q

      - name: Extract version from tag
        id: tag
        run: echo "version=${GITHUB_REF_NAME#v}" >> $GITHUB_OUTPUT

      - name: Verify pyproject version matches tag
        run: |
          uv run python - <<'PY'
          import tomllib
          v=tomllib.load(open("pyproject.toml","rb"))["project"]["version"]
          tv="${{ steps.tag.outputs.version }}"
          assert v==tv, f"pyproject version {v} != tag {tv}"
          PY

      - name: Ensure Unreleased is empty
        run: uv run python scripts/assert_unreleased_empty.py

      - name: Extract release notes from CHANGELOG.md
        run: uv run python scripts/extract_release_notes.py "${{ steps.tag.outputs.version }}"

      - name: Build (sdist + wheel)
        run: uv run python -m build

      - name: Publish to PyPI (Trusted Publishing)
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: dist/

      - name: Create GitHub Release + upload artifacts
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh release create "${GITHUB_REF_NAME}" \
            --title "${GITHUB_REF_NAME}" \
            --notes-file RELEASE_NOTES.md \
            dist/*
```

---

## PyPI publishing (recommended: Trusted Publishing)

### Setup (one-time)

1. Create the project on PyPI (or publish once manually).
2. In PyPI project settings, add a **Trusted Publisher**:

   * Provider: GitHub
   * Repo: your org/repo
   * Workflow: `.github/workflows/release.yml`
3. Ensure GitHub Actions has:

   * `permissions: id-token: write`

### Fallback (token-based)

If Trusted Publishing is not possible:

* Store `PYPI_API_TOKEN` as a GitHub secret.
* Replace publish step:

```yaml
- uses: pypa/gh-action-pypi-publish@release/v1
  with:
    password: ${{ secrets.PYPI_API_TOKEN }}
```

---

## Hardening checklist (recommended for serious OSS)

### Reproducibility

* Commit `uv.lock`.
* Use `uv sync --frozen` in CI.
* Build artifacts only after tests pass.

### Security

* Add dependency audit on tag builds (or every PR):

  * `uv run pip-audit`
* Add secret scanning:

  * `gitleaks` or `detect-secrets` in pre-commit + CI

### Release integrity

* Fail if:

  * tag version != pyproject version
  * changelog section missing
  * Unreleased is non-empty
  * tests/lint/typecheck fail
  * build fails

---

## Expected conventions

* Tags are `vX.Y.Z`.
* Changelog headers are `## [X.Y.Z] - YYYY-MM-DD`.
* `CHANGELOG.md` is authoritative release notes source.
* CI is authoritative publisher and release creator.
