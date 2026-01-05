"""Research phase processor for weld runs.

Generates research prompts and manages research artifact creation
based on the input specification.
"""

from pathlib import Path

RESEARCH_PROMPT_TEMPLATE = """\
You are a senior software architect analyzing a specification for planning.

## Task

Analyze the following specification and produce a comprehensive research document
that will inform the implementation plan.

## Specification

{spec_content}

## Research Requirements

Your research document should:

1. **Architecture Analysis**
   - Identify existing code patterns to follow
   - Note extension points and integration boundaries
   - Flag potential conflicts with existing systems

2. **Dependency Mapping**
   - External dependencies required
   - Internal module dependencies
   - Version constraints or compatibility concerns

3. **Risk Assessment**
   - Technical risks and mitigation strategies
   - Areas requiring prototyping or spikes
   - Performance or security considerations

4. **Open Questions**
   - Ambiguities in the specification
   - Decisions that need human input
   - Alternative approaches worth considering

## Output Format

Write a markdown document with clear sections. Use file:line references
where applicable (no code snippets).
"""


def generate_research_prompt(spec_content: str) -> str:
    """Generate research prompt from specification content.

    Args:
        spec_content: The specification markdown content

    Returns:
        Formatted prompt for AI research generation
    """
    return RESEARCH_PROMPT_TEMPLATE.format(spec_content=spec_content)


def write_research_prompt(research_dir: Path, prompt: str) -> Path:
    """Write research prompt to file.

    Args:
        research_dir: Path to run's research/ directory
        prompt: The generated prompt content

    Returns:
        Path to the written prompt file
    """
    prompt_path = research_dir / "prompt.md"
    prompt_path.write_text(prompt)
    return prompt_path


def import_research(research_dir: Path, content: str) -> Path:
    """Import AI-generated research content.

    Args:
        research_dir: Path to run's research/ directory
        content: The research markdown content

    Returns:
        Path to the written research file
    """
    research_path = research_dir / "research.md"
    research_path.write_text(content)
    return research_path


def get_research_content(research_dir: Path) -> str | None:
    """Get current research content if it exists.

    Args:
        research_dir: Path to run's research/ directory

    Returns:
        Research content or None if not yet imported
    """
    research_path = research_dir / "research.md"
    if research_path.exists():
        return research_path.read_text()
    return None
