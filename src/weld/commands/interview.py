"""Interview CLI command for specification refinement.

Two-step workflow:
1. `weld interview generate <spec.md>` - Generate questionnaire with clarifying questions
2. `weld interview apply <questionnaire.md>` - Apply user's answers to update spec
"""

from pathlib import Path
from typing import Annotated

import typer

from ..completions import complete_markdown_file
from ..config import load_config
from ..core import get_weld_dir, validate_input_file
from ..core.interview_engine import apply_questionnaire, generate_questionnaire
from ..output import get_output_context
from ..services import ClaudeError, GitError, get_repo_root, track_session_activity

# Create interview app with subcommands
interview_app = typer.Typer(
    help="Interview workflow for specification refinement",
    no_args_is_help=True,
)


@interview_app.command("generate")
def generate(
    file: Annotated[
        Path,
        typer.Argument(
            help="Markdown file to generate questionnaire for",
            autocompletion=complete_markdown_file,
        ),
    ],
    focus: Annotated[
        str | None,
        typer.Option("--focus", "-f", help="Topic to focus questions on"),
    ] = None,
    track: Annotated[
        bool,
        typer.Option("--track", help="Track session activity for this command"),
    ] = False,
) -> None:
    """Generate an interview questionnaire for a specification.

    Creates a markdown file with multiple-choice questions about ambiguities
    and hidden assumptions in the specification. Edit the questionnaire to
    mark your answers, then run `weld interview apply` to update the spec.

    Example:
        weld interview generate spec.md
        # Edit the generated questionnaire...
        weld interview apply .weld/interviews/spec-interview-*.md
    """
    out = get_output_context()

    # Validate input file
    if error := validate_input_file(file, must_be_markdown=True, param_name="file"):
        out.error(error[0], next_action=error[1])
        raise typer.Exit(1)

    # Get repo root and weld dir
    try:
        repo_root = get_repo_root()
        weld_dir = get_weld_dir(repo_root)
    except GitError:
        repo_root = None
        weld_dir = None

    # Load config
    config = load_config(weld_dir) if weld_dir else load_config(file.parent)

    # Determine output directory
    output_dir = weld_dir / "interviews" if weld_dir else None

    def _generate() -> Path | None:
        return generate_questionnaire(
            document_path=file,
            focus=focus,
            output_dir=output_dir,
            console=out.console,
            dry_run=out.dry_run,
            config=config,
        )

    try:
        if track and weld_dir and repo_root and weld_dir.exists():
            with track_session_activity(weld_dir, repo_root, "interview"):
                result = _generate()
        else:
            result = _generate()

        if result is None and not out.dry_run:
            out.error("Failed to generate questionnaire")
            raise typer.Exit(1)

    except ClaudeError as e:
        out.error(f"Interview failed: {e}")
        raise typer.Exit(21) from None
    except KeyboardInterrupt:
        out.console.print("\n[yellow]Interview cancelled[/yellow]")
        raise typer.Exit(0) from None


@interview_app.command("apply")
def apply(
    questionnaire: Annotated[
        Path,
        typer.Argument(
            help="Completed questionnaire file with marked answers",
            autocompletion=complete_markdown_file,
        ),
    ],
    track: Annotated[
        bool,
        typer.Option("--track", help="Track session activity for this command"),
    ] = False,
) -> None:
    """Apply questionnaire answers to update the source specification.

    Reads the completed questionnaire (with [x] marked answers) and uses
    Claude to integrate the chosen options into the original spec.

    Example:
        weld interview apply .weld/interviews/spec-interview-20240124-123456.md
    """
    out = get_output_context()

    # Validate questionnaire file
    if error := validate_input_file(
        questionnaire, must_be_markdown=True, param_name="questionnaire"
    ):
        out.error(error[0], next_action=error[1])
        raise typer.Exit(1)

    # Get repo root and weld dir
    try:
        repo_root = get_repo_root()
        weld_dir = get_weld_dir(repo_root)
    except GitError:
        repo_root = None
        weld_dir = None

    # Load config
    config = load_config(weld_dir) if weld_dir else load_config(questionnaire.parent)

    def _apply() -> bool:
        return apply_questionnaire(
            questionnaire_path=questionnaire,
            console=out.console,
            dry_run=out.dry_run,
            config=config,
        )

    try:
        if track and weld_dir and repo_root and weld_dir.exists():
            with track_session_activity(weld_dir, repo_root, "interview-apply"):
                modified = _apply()
        else:
            modified = _apply()

        if modified:
            out.console.print("[green]Specification updated successfully[/green]")
        elif not out.dry_run:
            out.console.print("[yellow]No changes made[/yellow]")

    except ClaudeError as e:
        out.error(f"Apply failed: {e}")
        raise typer.Exit(21) from None
    except ValueError as e:
        out.error(str(e))
        raise typer.Exit(1) from None
    except KeyboardInterrupt:
        out.console.print("\n[yellow]Apply cancelled[/yellow]")
        raise typer.Exit(0) from None
