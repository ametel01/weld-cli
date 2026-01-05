"""Discover engine for codebase analysis.

Generates architecture documentation from existing codebases,
providing context for brownfield development planning.
"""

from pathlib import Path

DISCOVER_PROMPT_TEMPLATE = """You are a senior software architect analyzing an existing codebase.

## Task

Analyze the codebase and produce a comprehensive architecture document that will
inform future development.

## Focus Areas

{focus_areas}

## Analysis Requirements

Your document should include:

1. **High-Level Architecture**
   - System overview and design patterns
   - Key components and their responsibilities
   - Data flow between components

2. **Directory Structure**
   - Purpose of each major directory
   - Naming conventions used
   - File organization patterns

3. **Key Files** (file:line references only, no code snippets)
   - Entry points and main modules
   - Configuration files
   - Critical business logic locations

4. **Integration Points**
   - External APIs and services
   - Database connections
   - File system dependencies

5. **Testing Patterns**
   - Test organization
   - Mocking strategies
   - Coverage patterns

## Output Format

Write a markdown document using file:line references. Example:
- Authentication logic: `src/auth/handler.py:45-120`
- Database models: `src/models/user.py:12`

Do NOT include code snippets - only file:line references.
"""


def generate_discover_prompt(focus_areas: str | None = None) -> str:
    """Generate discover prompt for codebase analysis.

    Args:
        focus_areas: Optional specific areas to focus on

    Returns:
        Formatted prompt for AI discovery
    """
    areas = focus_areas or "Analyze the entire codebase holistically."
    return DISCOVER_PROMPT_TEMPLATE.format(focus_areas=areas)


def get_discover_dir(weld_dir: Path) -> Path:
    """Get or create discover directory.

    Args:
        weld_dir: Path to .weld directory

    Returns:
        Path to .weld/discover/ directory
    """
    discover_dir = weld_dir / "discover"
    discover_dir.mkdir(exist_ok=True)
    return discover_dir
