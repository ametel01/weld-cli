"""Commit command implementation."""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import typer

from ..config import load_config
from ..core import get_weld_dir, log_command
from ..output import get_output_context
from ..services import (
    GitError,
    TranscriptError,
    commit_file,
    get_diff,
    get_repo_root,
    has_staged_changes,
    is_file_staged,
    run_git,
    run_transcript_gist,
    stage_all,
)
from ..services.claude import ClaudeError, run_claude


def _generate_commit_prompt(diff: str, changelog: str) -> str:
    """Generate prompt for Claude to create commit message and CHANGELOG entry."""
    return f"""Analyze this git diff and generate:
1. A commit message
2. A CHANGELOG entry

## Commit Message Rules
- Use imperative mood ("Add feature" not "Added feature")
- First line: concise summary under 72 chars
- If needed, blank line then detailed explanation
- Focus on WHY the change was made, not just WHAT
- NEVER mention Claude, AI, or automated tools
- NEVER include any footer or Co-Authored-By trailer

## CHANGELOG Rules
- Follow Keep a Changelog format
- Categorize under: Added, Changed, Deprecated, Removed, Fixed, Security
- Be concise but informative
- Use bullet points with `-`

## Current CHANGELOG [Unreleased] Section
```
{changelog}
```

## Git Diff
```diff
{diff}
```

## Output Format
Respond in EXACTLY this format (including the markers):

<commit_message>
Your commit message here (first line is subject, optional body after blank line)
</commit_message>

<changelog_entry>
### Category
- Entry description here
</changelog_entry>

If no CHANGELOG entry is needed (trivial change), output empty changelog_entry tags."""


def _parse_claude_response(response: str) -> tuple[str, str]:
    """Parse commit message and changelog entry from Claude response.

    Returns:
        Tuple of (commit_message, changelog_entry)
    """
    # Extract commit message
    commit_match = re.search(
        r"<commit_message>\s*(.*?)\s*</commit_message>",
        response,
        re.DOTALL,
    )
    commit_msg = commit_match.group(1).strip() if commit_match else ""

    # Extract changelog entry
    changelog_match = re.search(
        r"<changelog_entry>\s*(.*?)\s*</changelog_entry>",
        response,
        re.DOTALL,
    )
    changelog_entry = changelog_match.group(1).strip() if changelog_match else ""

    return commit_msg, changelog_entry


def _normalize_entry(entry: str) -> str:
    """Normalize changelog entry for duplicate comparison.

    Strips whitespace and converts to lowercase for fuzzy matching.
    """
    # Extract just the bullet points, ignoring headers
    lines = []
    for line in entry.strip().split("\n"):
        stripped = line.strip()
        if stripped.startswith("-"):
            # Normalize: lowercase, strip, remove extra whitespace
            normalized = " ".join(stripped.lower().split())
            lines.append(normalized)
    return "\n".join(lines)


def _update_changelog(repo_root: Path, entry: str) -> bool:
    """Update CHANGELOG.md with new entry under [Unreleased].

    Returns:
        True if changelog was updated, False otherwise
    """
    changelog_path = repo_root / "CHANGELOG.md"
    if not changelog_path.exists():
        return False

    if not entry:
        return False

    content = changelog_path.read_text()

    # Find [Unreleased] section and insert entry after it
    unreleased_pattern = r"(## \[Unreleased\])\n"
    match = re.search(unreleased_pattern, content)

    if not match:
        return False

    # Check for duplicate entry (compare normalized bullet points)
    normalized_entry = _normalize_entry(entry)
    # Extract existing unreleased section
    unreleased_match = re.search(
        r"## \[Unreleased\]\n(.*?)(?=\n## \[|$)",
        content,
        re.DOTALL,
    )
    if unreleased_match:
        existing_content = unreleased_match.group(1)
        normalized_existing = _normalize_entry(existing_content)
        # Check if entry already exists
        for entry_line in normalized_entry.split("\n"):
            if entry_line and entry_line in normalized_existing:
                return False  # Duplicate found, skip

    # Insert entry after [Unreleased] header
    insert_pos = match.end()
    new_content = content[:insert_pos] + "\n" + entry + "\n" + content[insert_pos:]
    changelog_path.write_text(new_content)
    return True


def commit(
    all: bool = typer.Option(False, "--all", "-a", help="Stage all changes before committing"),
    skip_transcript: bool = typer.Option(False, "--skip-transcript", help="Skip transcript upload"),
    skip_changelog: bool = typer.Option(False, "--skip-changelog", help="Skip CHANGELOG.md update"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress streaming output"),
    edit: bool = typer.Option(False, "--edit", "-e", help="Edit message in $EDITOR before commit"),
) -> None:
    """Auto-generate commit message from diff, update CHANGELOG, and commit with transcript.

    By default, only commits staged changes. Use -a/--all to stage all changes first.
    Use -e/--edit to review and modify the generated commit message before committing.
    """
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)

    # Check if weld is initialized
    if not weld_dir.exists():
        ctx.error("Weld not initialized. Run 'weld init' first.")
        raise typer.Exit(1) from None

    config = load_config(weld_dir)

    # Stage all changes if requested
    if all:
        stage_all(cwd=repo_root)

    # Verify staged changes exist
    if not has_staged_changes(cwd=repo_root):
        ctx.error("No changes to commit")
        raise typer.Exit(20) from None

    # Get staged diff
    diff = get_diff(staged=True, cwd=repo_root)
    if not diff:
        ctx.error("No diff content to analyze")
        raise typer.Exit(20) from None

    # Read current changelog for context
    changelog_path = repo_root / "CHANGELOG.md"
    changelog_unreleased = ""
    if changelog_path.exists():
        content = changelog_path.read_text()
        # Extract [Unreleased] section
        unreleased_match = re.search(
            r"## \[Unreleased\]\n(.*?)(?=\n## \[|$)",
            content,
            re.DOTALL,
        )
        if unreleased_match:
            changelog_unreleased = unreleased_match.group(1).strip()

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would analyze diff and create commit")
        ctx.console.print(f"  Stage all: {all}")
        ctx.console.print(f"  Diff size: {len(diff)} chars")
        ctx.console.print(f"  Skip changelog: {skip_changelog}")
        if not skip_transcript:
            ctx.console.print("  Would upload transcript gist and add trailer")
        return

    # Generate commit message using Claude
    ctx.console.print("[cyan]Generating commit message...[/cyan]")
    prompt = _generate_commit_prompt(diff, changelog_unreleased)

    try:
        response = run_claude(
            prompt,
            exec_path=config.claude.exec,
            model=config.claude.model,
            cwd=repo_root,
            stream=not quiet,
        )
    except ClaudeError as e:
        ctx.error(f"Failed to generate commit message: {e}")
        raise typer.Exit(21) from None

    commit_msg, changelog_entry = _parse_claude_response(response)

    if not commit_msg:
        ctx.error("Could not parse commit message from Claude response")
        ctx.console.print("[dim]Claude response:[/dim]")
        ctx.console.print(f"[dim]{response[:500]}{'...' if len(response) > 500 else ''}[/dim]")
        raise typer.Exit(23) from None

    ctx.console.print("")  # Newline after streaming output
    ctx.console.print(f"[green]Commit message:[/green]\n{commit_msg}")

    # Allow user to edit commit message if requested
    if edit:
        editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "vi"))
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(commit_msg)
            edit_file = Path(f.name)
        try:
            result = subprocess.run([editor, str(edit_file)])
            if result.returncode != 0:
                ctx.error(f"Editor exited with code {result.returncode}")
                edit_file.unlink()
                raise typer.Exit(24) from None
            commit_msg = edit_file.read_text().strip()
            if not commit_msg:
                ctx.error("Commit message is empty after editing")
                edit_file.unlink()
                raise typer.Exit(24) from None
        finally:
            if edit_file.exists():
                edit_file.unlink()
        ctx.console.print(f"[green]Edited commit message:[/green]\n{commit_msg}")

    # Update CHANGELOG if entry was generated
    if not skip_changelog and changelog_entry:
        # Check if CHANGELOG was already staged before we modify it
        changelog_was_staged = is_file_staged("CHANGELOG.md", cwd=repo_root)

        if _update_changelog(repo_root, changelog_entry):
            ctx.console.print("[green]Updated CHANGELOG.md[/green]")
            # Only stage CHANGELOG if it wasn't already staged (preserve user's staged hunks)
            if not changelog_was_staged:
                run_git("add", "CHANGELOG.md", cwd=repo_root)
            else:
                ctx.console.print(
                    "[yellow]CHANGELOG.md was already staged - please review and re-stage[/yellow]"
                )
        else:
            ctx.console.print("[yellow]Could not update CHANGELOG.md[/yellow]")

    # Upload transcript and add gist URL to commit message
    gist_url = None
    if not skip_transcript:
        ctx.console.print("[cyan]Uploading transcript...[/cyan]")
        try:
            result = run_transcript_gist(
                exec_path=config.claude.transcripts.exec,
                visibility=config.claude.transcripts.visibility,
                cwd=repo_root,
            )
            if result.gist_url:
                gist_url = result.gist_url
                commit_msg = f"{commit_msg}\n\n{config.git.commit_trailer_key}: {gist_url}"
            else:
                ctx.console.print("[yellow]Warning: Could not get transcript gist URL[/yellow]")
        except TranscriptError as e:
            ctx.console.print(f"[yellow]Warning: Transcript upload failed: {e}[/yellow]")

    # Write message to temp file and commit
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(commit_msg)
        msg_file = Path(f.name)

    try:
        sha = commit_file(msg_file, cwd=repo_root)
    except GitError as e:
        msg_file.unlink()
        ctx.error(f"Commit failed: {e}")
        raise typer.Exit(22) from None
    finally:
        if msg_file.exists():
            msg_file.unlink()

    ctx.success(f"Committed: {sha[:8]}")
    if gist_url:
        ctx.console.print(f"  Transcript: {gist_url}")

    # Log to history (use first line of commit message, more meaningful than diff)
    first_line = commit_msg.split("\n")[0]
    log_command(weld_dir, "commit", first_line, sha)
