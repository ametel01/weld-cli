"""Interview engine for interactive specification refinement.

Uses simple stdin/stdout for v1 (Decision: avoid prompt_toolkit dependency).
"""

from pathlib import Path

from rich.console import Console

INTERVIEW_SYSTEM_PROMPT = """You are helping refine a specification document through Q&A.

## Rules

1. Ask ONE question at a time
2. Focus on requirements (WHAT), not implementation (HOW)
3. If you detect contradictions, pause and ask for clarification
4. Questions should help make the spec more precise and complete
5. When you have enough information, say "INTERVIEW_COMPLETE"

## Current Document

{document_content}

## Focus Area (if specified)

{focus_area}

## Your Task

Based on the document above, ask your first clarifying question.
"""


def generate_interview_prompt(document_content: str, focus: str | None = None) -> str:
    """Generate interview prompt for spec refinement.

    Args:
        document_content: Current specification content
        focus: Optional area to focus questions on

    Returns:
        Formatted prompt for AI interviewer
    """
    focus_area = focus or "No specific focus - ask about any unclear areas."
    return INTERVIEW_SYSTEM_PROMPT.format(
        document_content=document_content,
        focus_area=focus_area,
    )


def run_interview_loop(
    document_path: Path,
    focus: str | None = None,
    console: Console | None = None,
    dry_run: bool = False,
) -> bool:
    """Run interactive interview loop.

    Uses simple stdin/stdout for v1.

    Args:
        document_path: Path to document being refined
        focus: Optional focus area
        console: Rich console for output (uses default if None)
        dry_run: If True, don't write changes to disk

    Returns:
        True if document was modified
    """
    con = console or Console()
    content = document_path.read_text()
    original_content = content
    modified = False
    answers: list[str] = []

    if dry_run:
        con.print("[cyan][DRY RUN][/cyan] Would run interview session on:")
        con.print(f"  {document_path}")
        con.print("\nNo changes will be written.")
        return False

    con.print("\n[bold]=== Interview Session ===[/bold]")
    con.print(f"Refining: {document_path}")
    con.print("Type 'quit' to exit, 'save' to save changes\n")

    # Generate initial prompt
    prompt = generate_interview_prompt(content, focus)
    con.print("[dim]Initial prompt generated. Copy to Claude and paste responses here.[/dim]\n")
    con.print("=" * 60)
    # Truncate at paragraph boundary if too long
    if len(prompt) > 500:
        truncate_pos = prompt.rfind("\n\n", 0, 500)
        if truncate_pos == -1:
            truncate_pos = 500
        con.print(prompt[:truncate_pos] + "\n...")
    else:
        con.print(prompt)
    con.print("=" * 60)

    while True:
        try:
            user_input = input("\nYour response (or 'quit'/'save'): ").strip()
        except EOFError:
            break

        if user_input.lower() == "quit":
            if modified:
                save = input("Save changes before quitting? (y/n): ").strip().lower()
                if save == "y":
                    document_path.write_text(content)
                    con.print(f"[green]Saved to {document_path}[/green]")
            break

        if user_input.lower() == "save":
            document_path.write_text(content)
            con.print(f"[green]Saved to {document_path}[/green]")
            continue

        if "INTERVIEW_COMPLETE" in user_input:
            con.print("\n[bold]Interview complete![/bold]")
            if modified:
                document_path.write_text(content)
                con.print(f"[green]Final document saved to {document_path}[/green]")
            break

        if not user_input:
            continue

        # Record the answer and append to document as notes
        answers.append(user_input)
        content = _append_interview_note(content, user_input, len(answers))
        modified = content != original_content
        con.print(f"[green]Answer #{len(answers)} recorded and appended to document[/green]")

    return modified


def _append_interview_note(content: str, answer: str, answer_num: int) -> str:
    """Append an interview answer as a note to the document.

    Args:
        content: Current document content
        answer: The answer to append
        answer_num: The answer number for labeling

    Returns:
        Updated content with answer appended
    """
    # Add interview notes section if not present
    notes_header = "\n\n---\n\n## Interview Notes\n\n"
    if "## Interview Notes" not in content:
        content += notes_header

    # Append the answer
    content += f"### Q{answer_num}\n\n{answer}\n\n"
    return content
