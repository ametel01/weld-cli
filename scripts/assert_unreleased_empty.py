#!/usr/bin/env python3
"""Assert that the Unreleased section in CHANGELOG.md is empty."""

import re
from pathlib import Path


def main() -> None:
    text = Path("CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^##\s+\[Unreleased\]\n(.*?)(?=^##\s+\[|\Z)", text, re.S | re.M)

    if m and m.group(1).strip():
        raise SystemExit(
            "Unreleased section is not empty — "
            "move entries into the release section before tagging."
        )


if __name__ == "__main__":
    main()
