"""Interview engine for interactive specification refinement.

Uses simple stdin/stdout for v1 (Decision: avoid prompt_toolkit dependency).
"""

from pathlib import Path

from rich.console import Console

from ..config import WeldConfig
from .prompt_customizer import apply_customization, get_default_focus

INTERVIEW_SYSTEM_PROMPT = """\
You are an expert technical interviewer helping flesh out a specification document.

## Interview Scope

Ask about literally anything relevant to completing the spec:
- Technical implementation details and architecture choices
- UI & UX considerations
- Concerns and edge cases
- Tradeoffs between approaches
- Integration points and dependencies
- Error handling and failure modes
- Performance and scalability implications
- Security considerations

## Rules

1. Use the AskUserQuestion tool to ask questions - ONE question at a time
2. Be very in-depth - dig into non-trivial details the author may have overlooked
3. Avoid obvious questions - surface hidden assumptions and make implicit requirements explicit
4. If you detect contradictions or gaps, pause and ask for clarification
5. Continue interviewing until the spec is comprehensive and actionable

## Current Document

{document_path}:
```
{document_content}
```

## Focus Area (if specified)

{focus_area}

## Your Task

Interview me in detail about this document. When the interview is complete, rewrite the
specification in place to `{document_path}` incorporating all gathered information.
"""


def generate_interview_prompt(
    document_path: Path,
    document_content: str,
    focus: str | None = None,
) -> str:
    """Generate interview prompt for spec refinement.

    Args:
        document_path: Path to the specification document
        document_content: Current specification content
        focus: Optional area to focus questions on

    Returns:
        Formatted prompt for AI interviewer
    """
    focus_area = focus or "No specific focus - ask about any unclear areas."
    return INTERVIEW_SYSTEM_PROMPT.format(
        document_path=document_path,
        document_content=document_content,
        focus_area=focus_area,
    )


def run_interview_loop(
    document_path: Path,
    focus: str | None = None,
    console: Console | None = None,
    dry_run: bool = False,
    config: WeldConfig | None = None,
) -> bool:
    """Generate interview prompt for use with Claude Code.

    The prompt instructs the AI to interview the user and rewrite the
    document in place when complete.

    Args:
        document_path: Path to document being refined
        focus: Optional focus area
        console: Rich console for output (uses default if None)
        dry_run: If True, just show what would happen
        config: Optional WeldConfig for prompt customization

    Returns:
        True (prompt was generated successfully)
    """
    con = console or Console()
    content = document_path.read_text()

    if dry_run:
        con.print("[cyan][DRY RUN][/cyan] Would generate interview prompt for:")
        con.print(f"  {document_path}")
        return False

    # Resolve effective focus (explicit focus takes precedence over default)
    effective_focus = focus
    if config:
        effective_focus = get_default_focus("interview", config, focus)

    # Generate the prompt for Claude Code
    prompt = generate_interview_prompt(document_path, content, effective_focus)

    # Apply customization if config is provided
    if config:
        prompt = apply_customization(prompt, "interview", config)

    con.print(prompt)

    return True
