#!/usr/bin/env python3
"""Extract release notes for a specific version from CHANGELOG.md."""

import re
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: extract_release_notes.py VERSION")

    version = sys.argv[1]
    text = Path("CHANGELOG.md").read_text(encoding="utf-8")

    # Match section header and capture content until next section or EOF
    pattern = rf"^##\s+\[{re.escape(version)}\][^\n]*\n(.*?)(?=^##\s+\[|\Z)"
    m = re.search(pattern, text, re.S | re.M)
    if not m:
        raise SystemExit(f"CHANGELOG.md missing section for [{version}]")

    notes = m.group(1).strip()
    Path("RELEASE_NOTES.md").write_text(notes + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
