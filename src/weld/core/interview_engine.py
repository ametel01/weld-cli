"""Interview engine for specification refinement via questionnaire.

Two-step process:
1. Generate: Analyze spec and produce a questionnaire with multi-choice questions
2. Apply: Read user's answers and update the spec accordingly
"""

from datetime import datetime
from pathlib import Path

from rich.console import Console

from ..config import WeldConfig
from ..services.claude import run_claude
from .prompt_customizer import apply_customization, get_default_focus

# Prompt for generating the questionnaire
QUESTIONNAIRE_PROMPT = """\
You are an expert technical interviewer analyzing a specification document.

## Your Task

Generate a questionnaire with 5-10 clarifying questions about this specification.
Each question should:
- Surface a hidden assumption or ambiguity
- Offer 2-4 concrete options (not vague choices)
- Include brief explanations for each option
- Help make implicit requirements explicit

## Question Categories to Consider

- Technical implementation choices (languages, frameworks, patterns)
- Architecture decisions (monolith vs microservices, sync vs async)
- Data modeling and storage
- Error handling and edge cases
- Security and authentication
- Performance and scalability requirements
- Integration points and dependencies
- User experience considerations

## Current Document

Path: {document_path}

```markdown
{document_content}
```

## Focus Area

{focus_area}

## Output Format

Output ONLY the questionnaire in this exact markdown format:

```markdown
# Interview Questionnaire

**Source:** {document_path}
**Generated:** {timestamp}
**Focus:** {focus_area}

## Instructions

Answer each question by placing an `x` in the checkbox next to your choice.
For "Other" options, replace the blank with your custom answer.

When complete, run:
```
weld interview apply <this-file.md>
```

---

## Q1: [Short Question Title]

[Full question text explaining what decision needs to be made]

- [ ] **Option A** - [Brief explanation of this choice and its tradeoffs]
- [ ] **Option B** - [Brief explanation of this choice and its tradeoffs]
- [ ] **Option C** - [Brief explanation of this choice and its tradeoffs]
- [ ] Other: _______________

---

## Q2: [Short Question Title]

[Continue with more questions...]
```

Generate questions that will genuinely improve the specification's clarity and completeness.
Focus on non-obvious decisions that the author may not have considered.
"""

# Prompt for applying answers to the spec
APPLY_PROMPT = """\
You are an expert technical writer updating a specification based on interview answers.

## Your Task

Rewrite the specification document to incorporate the user's answers from the questionnaire.
For each answered question:
- Integrate the chosen option naturally into the spec
- Add relevant details, constraints, or requirements based on the choice
- Ensure consistency throughout the document

## Original Specification

Path: {document_path}

```markdown
{document_content}
```

## Completed Questionnaire

The user has answered the following questions (marked with [x]):

```markdown
{questionnaire_content}
```

## Output Format

Output ONLY the updated specification content (no code fences, no explanations).
The output will directly replace the original file content.

Preserve the document's overall structure and style while incorporating the answers.
Add new sections if needed to address the chosen options comprehensively.
"""


def generate_questionnaire(
    document_path: Path,
    focus: str | None = None,
    output_dir: Path | None = None,
    console: Console | None = None,
    dry_run: bool = False,
    config: WeldConfig | None = None,
) -> Path | None:
    """Generate an interview questionnaire for a specification.

    Args:
        document_path: Path to the specification document
        focus: Optional area to focus questions on
        output_dir: Directory to save questionnaire (default: .weld/interviews/)
        console: Rich console for output
        dry_run: If True, show what would happen without executing
        config: Optional WeldConfig for Claude settings

    Returns:
        Path to generated questionnaire, or None if dry_run

    Raises:
        ClaudeError: If Claude invocation fails
    """
    con = console or Console()
    content = document_path.read_text()

    # Resolve output directory
    if output_dir is None:
        output_dir = document_path.parent / ".weld" / "interviews"

    if dry_run:
        con.print("[cyan][DRY RUN][/cyan] Would generate questionnaire for:")
        con.print(f"  Source: {document_path}")
        con.print(f"  Output: {output_dir}/")
        if focus:
            con.print(f"  Focus: {focus}")
        return None

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Resolve effective focus
    effective_focus = focus
    if config:
        effective_focus = get_default_focus("interview", config, focus)
    focus_text = effective_focus or "No specific focus - ask about any unclear areas."

    # Generate timestamp for the questionnaire
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build the prompt
    prompt = QUESTIONNAIRE_PROMPT.format(
        document_path=document_path,
        document_content=content,
        focus_area=focus_text,
        timestamp=timestamp,
    )

    # Apply customization if config provided
    if config:
        prompt = apply_customization(prompt, "interview", config)

    # Get Claude settings
    exec_path = config.claude.exec if config else "claude"
    timeout = config.claude.timeout if config else 1800
    max_output_tokens = config.claude.max_output_tokens if config else 128000

    con.print(f"[bold]Generating questionnaire for:[/bold] {document_path.name}")
    if effective_focus:
        con.print(f"[dim]Focus: {effective_focus}[/dim]")
    con.print()

    # Invoke Claude to generate questionnaire
    result = run_claude(
        prompt=prompt,
        exec_path=exec_path,
        cwd=document_path.parent,
        timeout=timeout,
        stream=True,
        max_output_tokens=max_output_tokens,
    )

    # Extract markdown content (strip any code fences Claude might add)
    questionnaire = _extract_markdown(result)

    # Generate output filename
    stem = document_path.stem
    date_suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = output_dir / f"{stem}-interview-{date_suffix}.md"

    # Write questionnaire
    output_path.write_text(questionnaire)

    con.print()
    con.print(f"[green]Questionnaire saved to:[/green] {output_path}")
    con.print()
    con.print("[dim]Next steps:[/dim]")
    con.print(f"  1. Edit {output_path.name} and mark your answers with [x]")
    con.print(f"  2. Run: weld interview apply {output_path}")

    return output_path


def apply_questionnaire(
    questionnaire_path: Path,
    console: Console | None = None,
    dry_run: bool = False,
    config: WeldConfig | None = None,
) -> bool:
    """Apply questionnaire answers to update the source specification.

    Args:
        questionnaire_path: Path to the completed questionnaire
        console: Rich console for output
        dry_run: If True, show what would happen without executing
        config: Optional WeldConfig for Claude settings

    Returns:
        True if spec was updated, False otherwise

    Raises:
        ClaudeError: If Claude invocation fails
        ValueError: If questionnaire format is invalid
    """
    con = console or Console()
    questionnaire_content = questionnaire_path.read_text()

    # Extract source document path from questionnaire
    source_path = _extract_source_path(questionnaire_content)
    if source_path is None:
        raise ValueError(
            "Could not find source document path in questionnaire. "
            "Expected '**Source:** /path/to/file.md' in the header."
        )

    # Resolve relative paths against questionnaire location
    if not source_path.is_absolute():
        source_path = (questionnaire_path.parent / source_path).resolve()

    if not source_path.exists():
        raise ValueError(f"Source document not found: {source_path}")

    document_content = source_path.read_text()

    # Check if any answers are selected
    if "[x]" not in questionnaire_content.lower():
        con.print("[yellow]Warning:[/yellow] No answers selected in questionnaire.")
        con.print("Mark your choices with [x] before applying.")
        return False

    if dry_run:
        con.print("[cyan][DRY RUN][/cyan] Would apply questionnaire:")
        con.print(f"  Questionnaire: {questionnaire_path}")
        con.print(f"  Target: {source_path}")
        return False

    # Build the prompt
    prompt = APPLY_PROMPT.format(
        document_path=source_path,
        document_content=document_content,
        questionnaire_content=questionnaire_content,
    )

    # Apply customization if config provided
    if config:
        prompt = apply_customization(prompt, "interview", config)

    # Get Claude settings
    exec_path = config.claude.exec if config else "claude"
    timeout = config.claude.timeout if config else 1800
    max_output_tokens = config.claude.max_output_tokens if config else 128000

    con.print(f"[bold]Applying questionnaire to:[/bold] {source_path.name}")
    con.print()

    # Invoke Claude to generate updated spec
    result = run_claude(
        prompt=prompt,
        exec_path=exec_path,
        cwd=source_path.parent,
        timeout=timeout,
        stream=True,
        max_output_tokens=max_output_tokens,
    )

    # Extract the updated content
    updated_content = _extract_markdown(result)

    # Check if content actually changed
    if updated_content.strip() == document_content.strip():
        con.print("[yellow]No changes detected.[/yellow]")
        return False

    # Write updated spec
    source_path.write_text(updated_content)

    con.print()
    con.print(f"[green]Updated:[/green] {source_path}")
    return True


def _extract_markdown(text: str) -> str:
    """Extract markdown content, stripping code fences if present.

    Args:
        text: Raw output from Claude

    Returns:
        Clean markdown content
    """
    text = text.strip()

    # If wrapped in ```markdown ... ```, extract inner content
    if text.startswith("```markdown"):
        lines = text.split("\n")
        # Find closing fence
        end_idx = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end_idx = i
                break
        return "\n".join(lines[1:end_idx]).strip()

    # If wrapped in ``` ... ```, extract inner content
    if text.startswith("```"):
        lines = text.split("\n")
        end_idx = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end_idx = i
                break
        return "\n".join(lines[1:end_idx]).strip()

    return text


def _extract_source_path(questionnaire: str) -> Path | None:
    """Extract source document path from questionnaire header.

    Looks for: **Source:** /path/to/file.md

    Args:
        questionnaire: Questionnaire content

    Returns:
        Path to source document, or None if not found
    """
    import re

    # Match **Source:** followed by a path
    match = re.search(r"\*\*Source:\*\*\s*(.+?)(?:\n|$)", questionnaire)
    if match:
        path_str = match.group(1).strip()
        # Remove any trailing markdown or quotes
        path_str = path_str.strip("`\"'")
        return Path(path_str)
    return None


# Legacy function for backwards compatibility
def generate_interview_prompt(
    document_path: Path,
    document_content: str,
    focus: str | None = None,
) -> str:
    """Generate interview prompt for spec refinement.

    Deprecated: Use generate_questionnaire() instead.
    """
    focus_area = focus or "No specific focus - ask about any unclear areas."
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return QUESTIONNAIRE_PROMPT.format(
        document_path=document_path,
        document_content=document_content,
        focus_area=focus_area,
        timestamp=timestamp,
    )


# Legacy function for backwards compatibility
def run_interview_loop(
    document_path: Path,
    focus: str | None = None,
    console: Console | None = None,
    dry_run: bool = False,
    config: WeldConfig | None = None,
    cwd: Path | None = None,
) -> bool:
    """Generate questionnaire (legacy interface).

    Deprecated: Use generate_questionnaire() directly.
    """
    result = generate_questionnaire(
        document_path=document_path,
        focus=focus,
        console=console,
        dry_run=dry_run,
        config=config,
    )
    return result is not None
