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
    get_staged_files,
    has_staged_changes,
    is_file_staged,
    run_git,
    run_transcript_gist,
    stage_all,
    stage_files,
    unstage_all,
)
from ..services.claude import ClaudeError, run_claude


class CommitGroup:
    """A logical group of files to commit together."""

    def __init__(self, message: str, files: list[str], changelog_entry: str = ""):
        self.message = message
        self.files = files
        self.changelog_entry = changelog_entry


def _generate_commit_prompt(diff: str, staged_files: list[str], changelog: str) -> str:
    """Generate prompt for Claude to analyze diff and create logical commit groups."""
    files_list = "\n".join(f"- {f}" for f in staged_files)

    return f"""Analyze this git diff and determine if changes should be split into multiple commits.

## Staged Files
{files_list}

## Analysis Rules
1. Group files by logical change (e.g., "fix typo" vs "update version" vs "add docs")
2. Each group should be a coherent, atomic change
3. If ALL changes are tightly related, return a single commit
4. Consider: docs, version bumps, bug fixes, features, refactoring as separate categories

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
Return one or more commit blocks. If changes should be split, return multiple blocks.
Each block MUST have all three tags (files, commit_message, changelog_entry).
Order commits logically (foundational changes first).

<commit>
<files>
path/to/file1.py
path/to/file2.py
</files>
<commit_message>
Your commit message here
</commit_message>
<changelog_entry>
### Category
- Entry description
</changelog_entry>
</commit>

<commit>
<files>
path/to/other.md
</files>
<commit_message>
Another commit message
</commit_message>
<changelog_entry>
</changelog_entry>
</commit>

If no CHANGELOG entry is needed for a commit, leave changelog_entry empty."""


def _parse_commit_groups(response: str) -> list[CommitGroup]:
    """Parse multiple commit groups from Claude response.

    Returns:
        List of CommitGroup objects
    """
    groups = []

    # Find all <commit>...</commit> blocks
    commit_pattern = re.compile(r"<commit>\s*(.*?)\s*</commit>", re.DOTALL)
    commit_blocks = commit_pattern.findall(response)

    for block in commit_blocks:
        # Extract files
        files_match = re.search(r"<files>\s*(.*?)\s*</files>", block, re.DOTALL)
        files = []
        if files_match:
            files = [f.strip() for f in files_match.group(1).strip().split("\n") if f.strip()]

        # Extract commit message
        msg_match = re.search(r"<commit_message>\s*(.*?)\s*</commit_message>", block, re.DOTALL)
        message = msg_match.group(1).strip() if msg_match else ""

        # Extract changelog entry
        changelog_match = re.search(
            r"<changelog_entry>\s*(.*?)\s*</changelog_entry>", block, re.DOTALL
        )
        changelog_entry = changelog_match.group(1).strip() if changelog_match else ""

        if message and files:
            groups.append(CommitGroup(message, files, changelog_entry))

    return groups


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
    no_split: bool = typer.Option(False, "--no-split", help="Disable auto-split, force one commit"),
) -> None:
    """Auto-generate commit message from diff, update CHANGELOG, and commit with transcript.

    By default, analyzes the diff and automatically creates multiple commits if changes
    are logically separate. Use --no-split to force a single commit.

    Use -a/--all to stage all changes first.
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

    # Get staged diff and files
    diff = get_diff(staged=True, cwd=repo_root)
    if not diff:
        ctx.error("No diff content to analyze")
        raise typer.Exit(20) from None

    staged_files = get_staged_files(cwd=repo_root)

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
        ctx.console.print("[cyan][DRY RUN][/cyan] Would analyze diff and create commit(s)")
        ctx.console.print(f"  Stage all: {all}")
        ctx.console.print(f"  Files: {len(staged_files)}")
        ctx.console.print(f"  Diff size: {len(diff)} chars")
        ctx.console.print(f"  Auto-split: {not no_split}")
        ctx.console.print(f"  Skip changelog: {skip_changelog}")
        if not skip_transcript:
            ctx.console.print("  Would upload transcript gist and add trailer to last commit")
        return

    # Generate commit message(s) using Claude
    ctx.console.print("[cyan]Analyzing changes...[/cyan]")
    prompt = _generate_commit_prompt(diff, staged_files, changelog_unreleased)

    try:
        response = run_claude(
            prompt,
            exec_path=config.claude.exec,
            model=config.claude.model,
            cwd=repo_root,
            stream=not quiet,
            max_output_tokens=config.claude.max_output_tokens,
        )
    except ClaudeError as e:
        ctx.error(f"Failed to generate commit message: {e}")
        raise typer.Exit(21) from None

    commit_groups = _parse_commit_groups(response)

    if not commit_groups:
        ctx.error("Could not parse commit groups from Claude response")
        ctx.console.print("[dim]Claude response:[/dim]")
        ctx.console.print(f"[dim]{response[:500]}{'...' if len(response) > 500 else ''}[/dim]")
        raise typer.Exit(23) from None

    # If --no-split, merge all groups into one
    if no_split and len(commit_groups) > 1:
        merged_files = []
        merged_changelog = []
        for g in commit_groups:
            merged_files.extend(g.files)
            if g.changelog_entry:
                merged_changelog.append(g.changelog_entry)
        # Use first commit message as base
        merged_message = commit_groups[0].message
        commit_groups = [CommitGroup(merged_message, merged_files, "\n\n".join(merged_changelog))]
        ctx.console.print("[yellow]Merged into single commit (--no-split)[/yellow]")

    ctx.console.print("")  # Newline after streaming output
    ctx.console.print(f"[green]Identified {len(commit_groups)} commit(s):[/green]")
    for i, group in enumerate(commit_groups, 1):
        first_line = group.message.split("\n")[0]
        ctx.console.print(f"  {i}. {first_line} ({len(group.files)} files)")

    # Unstage everything first so we can stage per-group
    unstage_all(cwd=repo_root)

    # Track all created commits
    created_commits = []
    gist_url = None

    for i, group in enumerate(commit_groups):
        is_last = i == len(commit_groups) - 1
        ctx.console.print(f"\n[cyan]Creating commit {i + 1}/{len(commit_groups)}...[/cyan]")

        commit_msg = group.message

        # Allow user to edit commit message if requested (only for first or single commit)
        if edit and (len(commit_groups) == 1 or i == 0):
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

        # Stage only this group's files
        stage_files(group.files, cwd=repo_root)

        # Update CHANGELOG if entry was generated
        if not skip_changelog and group.changelog_entry:
            changelog_was_staged = is_file_staged("CHANGELOG.md", cwd=repo_root)

            if _update_changelog(repo_root, group.changelog_entry):
                ctx.console.print("[green]Updated CHANGELOG.md[/green]")
                if not changelog_was_staged:
                    run_git("add", "CHANGELOG.md", cwd=repo_root)
            else:
                ctx.console.print("[yellow]Could not update CHANGELOG.md[/yellow]")

        # Upload transcript for the LAST commit only
        if is_last and not skip_transcript:
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
            created_commits.append(sha[:8])
        except GitError as e:
            msg_file.unlink()
            ctx.error(f"Commit failed: {e}")
            raise typer.Exit(22) from None
        finally:
            if msg_file.exists():
                msg_file.unlink()

        first_line = commit_msg.split("\n")[0]
        ctx.success(f"Committed: {sha[:8]} - {first_line[:50]}")

        # Log to history
        log_command(weld_dir, "commit", first_line, sha)

    # Summary
    ctx.console.print(f"\n[green]✓ Created {len(created_commits)} commit(s)[/green]")
    if gist_url:
        ctx.console.print(f"  Transcript: {gist_url}")
