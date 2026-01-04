"""Tests for weld plan parsing."""

from weld.core.plan_parser import parse_steps, parse_steps_lenient, parse_steps_strict

STRICT_PLAN = """
## Step 1: Create config module

### Goal
Set up configuration handling.

### Changes
- Create src/config.py

### Acceptance criteria
- [ ] Config loads from TOML
- [ ] Defaults are sane

### Tests
- pytest tests/test_config.py

## Step 2: Build CLI

### Goal
Create the CLI entry point.

### Changes
- Create src/cli.py

### Acceptance criteria
- [ ] --help works

### Tests
- weld --help
"""

LENIENT_PLAN = """
1. Create config module
   Set up configuration handling.

2. Build CLI
   Create the CLI entry point.
"""


def test_parse_strict_format():
    steps = parse_steps_strict(STRICT_PLAN)
    assert len(steps) == 2
    assert steps[0].n == 1
    assert steps[0].title == "Create config module"
    assert "Config loads from TOML" in steps[0].acceptance_criteria
    assert steps[1].n == 2


def test_parse_lenient_format():
    steps = parse_steps_lenient(LENIENT_PLAN)
    assert len(steps) == 2
    assert steps[0].title == "Create config module"


def test_parse_steps_prefers_strict():
    steps, warnings = parse_steps(STRICT_PLAN)
    assert len(steps) == 2
    assert len(warnings) == 0


def test_parse_steps_falls_back_to_lenient():
    steps, warnings = parse_steps(LENIENT_PLAN)
    assert len(steps) == 2
    assert "lenient" in warnings[0].lower()
