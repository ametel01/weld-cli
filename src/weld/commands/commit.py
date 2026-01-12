"""Commit command implementation."""

import contextlib
import re
import tempfile
from datetime import datetime
from pathlib import Path

import typer

from ..config import WeldConfig, load_config
from ..core import get_weld_dir, log_command
from ..models.session import TrackedSession
from ..output import OutputContext, get_output_context
from ..services import (
    GitError,
    commit_file,
    get_diff,
    get_repo_root,
    get_staged_files,
    has_staged_changes,
    is_file_staged,
    run_git,
    stage_all,
    stage_files,
    unstage_all,
)
from ..services.claude import ClaudeError, run_claude
from ..services.gist_uploader import (
    GistError,
    generate_gist_description,
    generate_transcript_filename,
    upload_gist,
)
from ..services.session_detector import detect_current_session, get_session_id
from ..services.session_tracker import SessionRegistry, get_registry
from ..services.transcript_renderer import render_transcript


def _should_exclude_from_commit(file_path: str) -> bool:
    """Check if a file should be excluded from commits.

    Excludes .weld/ metadata files while keeping config.toml.
    This prevents internal tracking files from being committed.

    Args:
        file_path: Relative file path from repo root

    Returns:
        True if file should be excluded, False otherwise
    """
    # Normalize path separators
    normalized = file_path.replace("\\", "/")

    # Exclude .weld/ files except config.toml
    if normalized.startswith(".weld/"):
        return normalized != ".weld/config.toml"

    return False


def resolve_files_to_sessions(
    staged_files: list[str],
    registry: SessionRegistry,
) -> dict[str, list[str]]:
    """Map staged files to their originating sessions.

    Analyzes the session registry to determine which Claude session(s)
    created or modified each staged file. This enables session-based
    commit grouping for proper transcript attribution.

    Args:
        staged_files: List of staged file paths (relative to repo root)
        registry: Session registry containing tracked sessions

    Returns:
        Dict mapping session_id → list of files.
        Key "_untracked" for files not in any session.
    """
    file_to_session: dict[str, str] = {}

    # Build reverse map: file → most recent session that touched it
    for session in registry.sessions.values():
        for activity in session.activities:
            for f in activity.files_created + activity.files_modified:
                # Later activity overwrites earlier (most recent wins)
                file_to_session[f] = session.session_id

    # Group staged files by session
    result: dict[str, list[str]] = {}
    for f in staged_files:
        session_id = file_to_session.get(f, "_untracked")
        result.setdefault(session_id, []).append(f)

    return result


def prompt_untracked_grouping(
    untracked_files: list[str],
    most_recent_session: str | None,
) -> str | None:
    """Prompt user how to handle files not tracked to any session.

    When staged files aren't associated with any tracked Claude session,
    this function asks the user whether to attribute them to the most
    recent session or create a separate commit without a transcript.

    Args:
        untracked_files: List of files not tracked to any session
        most_recent_session: Session ID of most recent session, or None

    Returns:
        "attribute" - attribute to most recent session
        "separate" - create separate commit without transcript
        None - user cancelled
    """
    from rich.prompt import Prompt

    from ..output import get_output_context

    ctx = get_output_context()

    ctx.console.print("\n[yellow]The following files are not tracked to any session:[/yellow]")
    for f in untracked_files[:10]:  # Show first 10
        ctx.console.print(f"  - {f}")
    if len(untracked_files) > 10:
        ctx.console.print(f"  ... and {len(untracked_files) - 10} more")

    if most_recent_session:
        ctx.console.print("\nOptions:")
        ctx.console.print(f"  [1] Attribute to most recent session ({most_recent_session[:8]})")
        ctx.console.print("  [2] Create separate commit without transcript")
        ctx.console.print("  [3] Cancel")

        choice = Prompt.ask("Select", choices=["1", "2", "3"], default="1")
        if choice == "1":
            return "attribute"
        elif choice == "2":
            return "separate"
        return None
    else:
        ctx.console.print("\nNo tracked sessions available.")
        ctx.console.print("  [1] Create commit without transcript")
        ctx.console.print("  [2] Cancel")

        choice = Prompt.ask("Select", choices=["1", "2"], default="1")
        return "separate" if choice == "1" else None


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


def _merge_commit_groups(groups: list[CommitGroup]) -> CommitGroup:
    """Merge multiple commit groups into a single group.

    Used when --no-split is specified to combine all logical groups
    into a single commit.

    Args:
        groups: List of CommitGroup objects to merge

    Returns:
        Single CommitGroup with combined files and changelog entries
    """
    merged_files: list[str] = []
    merged_changelog: list[str] = []
    for g in groups:
        merged_files.extend(g.files)
        if g.changelog_entry:
            merged_changelog.append(g.changelog_entry)
    return CommitGroup(
        message=groups[0].message,
        files=merged_files,
        changelog_entry="\n\n".join(merged_changelog),
    )


def _commit_by_sessions(
    ctx: OutputContext,
    session_files: dict[str, list[str]],
    registry: SessionRegistry,
    config: WeldConfig,
    repo_root: Path,
    weld_dir: Path,
    skip_transcript: bool,
    skip_changelog: bool,
    quiet: bool,
) -> None:
    """Create commits grouped by session.

    Each tracked session gets its own commit with the transcript from that
    session attached. Untracked files get a separate commit without transcript.

    Error Recovery:
    - If a commit fails mid-way, remaining sessions stay in registry
    - Files for failed session remain staged
    - User can retry with `weld commit` after fixing the issue

    Args:
        ctx: Output context for console output
        session_files: Dict mapping session_id -> list of files
        registry: Session registry
        config: Weld configuration
        repo_root: Repository root path
        weld_dir: .weld directory path
        skip_transcript: Whether to skip transcript upload
        skip_changelog: Whether to skip changelog update
        quiet: Whether to suppress streaming output
    """
    ctx.console.print(f"[green]Creating {len(session_files)} commit(s) by session:[/green]")

    # Unstage everything first
    unstage_all(cwd=repo_root)

    # Sort sessions by first_seen (chronological order)
    def get_session_time(sid: str) -> datetime:
        session = registry.get(sid)
        return session.first_seen if session else datetime.min

    session_order = sorted(
        [sid for sid in session_files if sid != "_untracked"],
        key=get_session_time,
    )
    # Untracked files come last
    if "_untracked" in session_files:
        session_order.append("_untracked")

    created_commits: list[str] = []

    for session_id in session_order:
        files = session_files[session_id]
        is_untracked = session_id == "_untracked"
        session = registry.get(session_id) if not is_untracked else None

        label = "untracked files" if is_untracked else f"session {session_id[:8]}"
        ctx.console.print(f"\n[cyan]Creating commit for {label}...[/cyan]")

        # Stage files for this session
        stage_files(files, cwd=repo_root)

        # Generate commit message via Claude
        diff = get_diff(staged=True, cwd=repo_root)
        prompt = _generate_commit_prompt(diff, files, "")

        try:
            response = run_claude(
                prompt=prompt,
                exec_path=config.claude.exec,
                model=config.claude.model,
                cwd=repo_root,
                stream=not quiet,
                skip_permissions=True,
                max_output_tokens=config.claude.max_output_tokens,
            )
            groups = _parse_commit_groups(response)
            commit_msg = groups[0].message if groups else f"Update {len(files)} files"
            changelog_entry = groups[0].changelog_entry if groups else ""
        except ClaudeError as e:
            ctx.console.print(f"[yellow]Claude failed: {e}, using generic message[/yellow]")
            commit_msg = f"Update {len(files)} files"
            changelog_entry = ""

        # Upload transcript (only for tracked sessions)
        gist_url = None
        if not is_untracked and not skip_transcript and session and config.transcripts.enabled:
            try:
                session_path = Path(session.session_file)
                if session_path.exists():
                    transcript = render_transcript(session_path, config.project.name)
                    result = upload_gist(
                        content=transcript,
                        filename=generate_transcript_filename(config.project.name, session_id),
                        description=generate_gist_description(
                            config.project.name, commit_msg.split("\n")[0]
                        ),
                        public=config.transcripts.visibility == "public",
                        cwd=repo_root,
                    )
                    gist_url = result.gist_url
                else:
                    ctx.console.print(
                        "[yellow]Session file not found, skipping transcript[/yellow]"
                    )
            except GistError as e:
                ctx.console.print(f"[yellow]Transcript upload skipped: {e}[/yellow]")

        # Add trailer if gist uploaded
        if gist_url:
            commit_msg = f"{commit_msg}\n\n{config.git.commit_trailer_key}: {gist_url}"

        # Update changelog
        if not skip_changelog and changelog_entry:
            changelog_was_staged = is_file_staged("CHANGELOG.md", cwd=repo_root)
            if _update_changelog(repo_root, changelog_entry):
                ctx.console.print("[green]Updated CHANGELOG.md[/green]")
                if not changelog_was_staged:
                    run_git("add", "CHANGELOG.md", cwd=repo_root)

        # Create commit
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(commit_msg)
            msg_file = Path(f.name)

        try:
            sha = commit_file(msg_file, cwd=repo_root)
            created_commits.append(sha[:8])
        except GitError as e:
            msg_file.unlink(missing_ok=True)
            # Error recovery: show what succeeded before failure
            ctx.error(f"Commit failed for {label}: {e}")
            if created_commits:
                ctx.console.print(
                    f"[yellow]Created {len(created_commits)} commit(s) before failure:[/yellow]"
                )
                for commit_sha in created_commits:
                    ctx.console.print(f"  - {commit_sha}")
            remaining = len(session_order) - session_order.index(session_id)
            if remaining > 1:
                ctx.console.print(
                    f"[yellow]{remaining - 1} session(s) remaining - run 'weld commit'[/yellow]"
                )
            raise typer.Exit(22) from None
        finally:
            if msg_file.exists():
                msg_file.unlink()

        first_line = commit_msg.split("\n")[0]
        ctx.success(f"Committed: {sha[:8]} - {first_line[:50]}")

        # Prune session from registry ONLY after successful commit
        if not is_untracked:
            registry.prune_session(session_id)

        # Log to history
        log_command(weld_dir, "commit", first_line, sha)

    ctx.console.print(f"\n[green]✓ Created {len(created_commits)} commit(s)[/green]")


def _commit_with_fallback_transcript(
    ctx: OutputContext,
    staged_files: list[str],
    config: WeldConfig,
    repo_root: Path,
    weld_dir: Path,
    registry: SessionRegistry,
    skip_transcript: bool,
    skip_changelog: bool,
    quiet: bool,
    no_split: bool,
    changelog_unreleased: str,
) -> None:
    """Commit using Claude's logical grouping with transcript from most recent session.

    This is the fallback behavior when no sessions are tracked or when
    --no-session-split is used. It maintains backwards compatibility
    while still attaching transcripts from detected Claude sessions.

    Args:
        ctx: Output context for console output
        staged_files: List of staged file paths
        config: Weld configuration
        repo_root: Repository root path
        weld_dir: .weld directory path
        registry: Session registry for finding matching sessions
        skip_transcript: Whether to skip transcript upload
        skip_changelog: Whether to skip changelog update
        quiet: Whether to suppress streaming output
        no_split: Whether to force single commit
        changelog_unreleased: Current changelog unreleased section content
    """
    # Find ALL sessions that contributed to the staged files
    # This allows us to attach multiple transcripts (e.g., implement + review)
    # to the same commit for full context
    matching_sessions: list[tuple[TrackedSession, int]] = []

    for session in registry.sessions.values():
        matched_files = 0
        for activity in session.activities:
            for f in activity.files_created + activity.files_modified:
                if f in staged_files:
                    matched_files += 1

        if matched_files > 0:
            matching_sessions.append((session, matched_files))

    # Sort by number of matches (highest first) for better display
    matching_sessions.sort(key=lambda x: x[1], reverse=True)

    if matching_sessions:
        ctx.console.print("[dim]Found sessions matching staged files:[/dim]")
        for session, count in matching_sessions:
            # Determine session type from activities
            commands = {activity.command for activity in session.activities}
            cmd_label = ", ".join(sorted(commands))
            ctx.console.print(
                f"[dim]  - {session.session_id[:8]} ({cmd_label}): "
                f"{count}/{len(staged_files)} files[/dim]"
            )
    else:
        ctx.console.print(
            "[dim]No tracked sessions match staged files, "
            "will use most recent session if available[/dim]"
        )

    # Generate commit groups using Claude
    diff = get_diff(staged=True, cwd=repo_root)
    ctx.console.print("[cyan]Analyzing changes...[/cyan]")
    prompt = _generate_commit_prompt(diff, staged_files, changelog_unreleased)

    try:
        response = run_claude(
            prompt=prompt,
            exec_path=config.claude.exec,
            model=config.claude.model,
            cwd=repo_root,
            stream=not quiet,
            skip_permissions=True,
            max_output_tokens=config.claude.max_output_tokens,
        )
        commit_groups = _parse_commit_groups(response)
    except ClaudeError as e:
        ctx.error(f"Failed to generate commit message: {e}")
        raise typer.Exit(21) from None

    if not commit_groups:
        ctx.error("Could not parse commit groups from Claude response")
        ctx.console.print("[dim]Claude response:[/dim]")
        ctx.console.print(f"[dim]{response[:500]}{'...' if len(response) > 500 else ''}[/dim]")
        raise typer.Exit(23) from None

    # Force single commit if requested
    if no_split and len(commit_groups) > 1:
        commit_groups = [_merge_commit_groups(commit_groups)]
        ctx.console.print("[yellow]Merged into single commit (--no-split)[/yellow]")

    ctx.console.print("")  # Newline after streaming
    ctx.console.print(f"[green]Identified {len(commit_groups)} commit(s):[/green]")
    for i, group in enumerate(commit_groups, 1):
        first_line = group.message.split("\n")[0]
        ctx.console.print(f"  {i}. {first_line} ({len(group.files)} files)")

    # Unstage everything first
    unstage_all(cwd=repo_root)

    created_commits: list[str] = []
    all_gist_urls: list[str] = []

    for i, group in enumerate(commit_groups):
        is_last = i == len(commit_groups) - 1
        ctx.console.print(f"\n[cyan]Creating commit {i + 1}/{len(commit_groups)}...[/cyan]")

        commit_msg = group.message

        # Stage files for this group
        stage_files(group.files, cwd=repo_root)

        # Update changelog
        if not skip_changelog and group.changelog_entry:
            changelog_was_staged = is_file_staged("CHANGELOG.md", cwd=repo_root)
            if _update_changelog(repo_root, group.changelog_entry):
                ctx.console.print("[green]Updated CHANGELOG.md[/green]")
                if not changelog_was_staged:
                    run_git("add", "CHANGELOG.md", cwd=repo_root)
            else:
                ctx.console.print("[yellow]Could not update CHANGELOG.md[/yellow]")

        # Attach transcripts to LAST commit only
        # Upload one gist per matching session (e.g., implement + review)
        if is_last and not skip_transcript and config.transcripts.enabled:
            gist_urls: list[str] = []

            # Upload transcripts for all matching sessions
            if matching_sessions:
                ctx.console.print(
                    f"[cyan]Uploading {len(matching_sessions)} transcript(s)...[/cyan]"
                )
                for session, _count in matching_sessions:
                    session_file_path = Path(session.session_file)
                    if not session_file_path.exists():
                        ctx.console.print(
                            f"[yellow]Session file not found for {session.session_id[:8]}, "
                            "skipping transcript[/yellow]"
                        )
                        continue

                    try:
                        # Get command label for gist filename/description
                        commands = {activity.command for activity in session.activities}
                        cmd_label = "-".join(sorted(commands))

                        transcript = render_transcript(session_file_path, config.project.name)
                        first_line = commit_msg.split("\n")[0]
                        result = upload_gist(
                            content=transcript,
                            filename=generate_transcript_filename(
                                config.project.name,
                                f"{session.session_id}-{cmd_label}",
                            ),
                            description=generate_gist_description(
                                config.project.name,
                                f"{first_line} ({cmd_label})",
                            ),
                            public=config.transcripts.visibility == "public",
                            cwd=repo_root,
                        )
                        gist_urls.append(result.gist_url)
                        ctx.console.print(
                            f"[dim]  ✓ {session.session_id[:8]} ({cmd_label}): "
                            f"{result.gist_url}[/dim]"
                        )
                    except GistError as e:
                        ctx.console.print(
                            f"[yellow]Transcript upload failed for {session.session_id[:8]}: "
                            f"{e}[/yellow]"
                        )
            else:
                # Fallback: use most recent session if no matches
                most_recent_session = detect_current_session(repo_root)
                if most_recent_session:
                    ctx.console.print(
                        "[cyan]Uploading transcript from most recent session...[/cyan]"
                    )
                    try:
                        session_id = get_session_id(most_recent_session)
                        transcript = render_transcript(most_recent_session, config.project.name)
                        result = upload_gist(
                            content=transcript,
                            filename=generate_transcript_filename(config.project.name, session_id),
                            description=generate_gist_description(
                                config.project.name, commit_msg.split("\n")[0]
                            ),
                            public=config.transcripts.visibility == "public",
                            cwd=repo_root,
                        )
                        gist_urls.append(result.gist_url)
                    except (GistError, FileNotFoundError) as e:
                        ctx.console.print(f"[yellow]Transcript upload skipped: {e}[/yellow]")

            # Add all gist URLs as trailers
            if gist_urls:
                trailers = "\n".join(f"{config.git.commit_trailer_key}: {url}" for url in gist_urls)
                commit_msg = f"{commit_msg}\n\n{trailers}"
                all_gist_urls.extend(gist_urls)

        # Create commit
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

    ctx.console.print(f"\n[green]✓ Created {len(created_commits)} commit(s)[/green]")
    if all_gist_urls:
        if len(all_gist_urls) == 1:
            ctx.console.print(f"  Transcript: {all_gist_urls[0]}")
        else:
            ctx.console.print(f"  Transcripts ({len(all_gist_urls)}):")
            for url in all_gist_urls:
                ctx.console.print(f"    - {url}")


def commit(
    all: bool = typer.Option(False, "--all", "-a", help="Stage all changes before committing"),
    skip_transcript: bool = typer.Option(False, "--skip-transcript", help="Skip transcript upload"),
    skip_changelog: bool = typer.Option(False, "--skip-changelog", help="Skip CHANGELOG.md update"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress streaming output"),
    no_split: bool = typer.Option(False, "--no-split", help="Disable logical grouping, one commit"),
    no_session_split: bool = typer.Option(
        False, "--no-session-split", help="Disable session-based grouping"
    ),
) -> None:
    """Auto-generate commit message from diff, update CHANGELOG, and commit with transcript.

    By default, analyzes the diff and automatically creates multiple commits if changes
    are logically separate. Use --no-split to force a single commit.

    Use -a/--all to stage all changes first.
    Use --no-session-split to disable session-based grouping of files.
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

    # Filter out .weld/ metadata files (keep only config.toml)
    excluded_files = [f for f in staged_files if _should_exclude_from_commit(f)]

    # Unstage excluded files and warn user
    if excluded_files:
        ctx.console.print(
            f"[yellow]Excluding {len(excluded_files)} .weld/ metadata file(s) from commit[/yellow]"
        )
        # Unstage the excluded files
        for f in excluded_files:
            # File might not be staged, ignore errors
            with contextlib.suppress(GitError):
                run_git("restore", "--staged", f, cwd=repo_root)

        # Refresh staged files list after unstaging
        staged_files = get_staged_files(cwd=repo_root)

    if not staged_files:
        ctx.error("No files to commit after filtering .weld/ metadata")
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

    # Load session registry
    registry = get_registry(weld_dir)

    # Determine commit strategy: session-based or fallback
    use_session_flow = bool(registry.sessions) and not no_session_split

    if use_session_flow:
        # Session-based commit flow
        session_files = resolve_files_to_sessions(staged_files, registry)

        # Handle untracked files if there are also tracked files
        if "_untracked" in session_files and len(session_files) > 1:
            most_recent = (
                max(
                    registry.sessions.values(),
                    key=lambda s: s.last_activity,
                ).session_id
                if registry.sessions
                else None
            )

            choice = prompt_untracked_grouping(session_files["_untracked"], most_recent)
            if choice is None:
                ctx.console.print("[yellow]Cancelled[/yellow]")
                return
            elif choice == "attribute" and most_recent:
                session_files.setdefault(most_recent, []).extend(session_files.pop("_untracked"))
            # "separate" leaves _untracked as-is for its own commit

        # Dry run: preview session breakdown
        if ctx.dry_run:
            ctx.console.print("[cyan][DRY RUN][/cyan] Session breakdown:")
            ctx.console.print(f"  Total sessions: {len(session_files)}")
            for session_id, files in session_files.items():
                label = session_id[:8] if session_id != "_untracked" else "untracked"
                ctx.console.print(f"\n  [{label}] {len(files)} files:")
                for f in files[:5]:
                    ctx.console.print(f"    - {f}")
                if len(files) > 5:
                    ctx.console.print(f"    ... and {len(files) - 5} more")
            return

        # Execute session-based commits
        _commit_by_sessions(
            ctx=ctx,
            session_files=session_files,
            registry=registry,
            config=config,
            repo_root=repo_root,
            weld_dir=weld_dir,
            skip_transcript=skip_transcript,
            skip_changelog=skip_changelog,
            quiet=quiet,
        )
    else:
        # Fallback: Claude-based logical grouping with transcript from most recent session
        if ctx.dry_run:
            ctx.console.print("[cyan][DRY RUN][/cyan] Would analyze diff and create commit(s)")
            ctx.console.print(f"  Stage all: {all}")
            ctx.console.print(f"  Files: {len(staged_files)}")
            ctx.console.print(f"  Diff size: {len(diff)} chars")
            ctx.console.print(f"  Auto-split: {not no_split}")
            ctx.console.print(f"  Session-split: {not no_session_split}")
            ctx.console.print(f"  Skip changelog: {skip_changelog}")
            if not skip_transcript:
                ctx.console.print("  Would upload transcript gist and add trailer to last commit")
            return

        _commit_with_fallback_transcript(
            ctx=ctx,
            staged_files=staged_files,
            config=config,
            repo_root=repo_root,
            weld_dir=weld_dir,
            registry=registry,
            skip_transcript=skip_transcript,
            skip_changelog=skip_changelog,
            quiet=quiet,
            no_split=no_split,
            changelog_unreleased=changelog_unreleased,
        )
