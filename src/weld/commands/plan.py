"""Plan command implementations."""

import json
from pathlib import Path

import typer

from ..config import TaskType, load_config
from ..core import (
    LockError,
    acquire_lock,
    generate_codex_review_prompt,
    generate_plan_prompt,
    get_research_content,
    get_run_dir,
    get_weld_dir,
    parse_steps,
    release_lock,
)
from ..models import SpecRef
from ..output import get_output_context
from ..services import CodexError, GitError, extract_revised_plan, get_repo_root, run_codex


def plan_prompt(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
) -> None:
    """Generate plan prompt from spec and research."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    if not run_dir.exists():
        ctx.console.print(f"[red]Error: Run not found: {run}[/red]")
        raise typer.Exit(1)

    # Load spec reference
    spec_ref_path = run_dir / "inputs" / "spec.ref.json"
    if not spec_ref_path.exists():
        ctx.console.print("[red]Error: spec.ref.json not found[/red]")
        raise typer.Exit(1)

    spec_ref = SpecRef.model_validate_json(spec_ref_path.read_text())
    spec_path = spec_ref.absolute_path

    if not spec_path.exists():
        ctx.console.print(f"[red]Error: Spec file not found: {spec_path}[/red]")
        raise typer.Exit(1)

    spec_content = spec_path.read_text()

    # Check for research content
    research_dir = run_dir / "research"
    research_content: str | None = None
    if research_dir.exists():
        research_content = get_research_content(research_dir)

    # Get model config for plan generation task
    model_cfg = config.get_task_model(TaskType.PLAN_GENERATION)
    model_info = f" ({model_cfg.model})" if model_cfg.model else ""

    # Generate plan prompt
    plan_prompt_content = generate_plan_prompt(
        spec_content, spec_path, research_content=research_content
    )

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would generate plan prompt:")
        ctx.console.print(f"  Run: {run}")
        ctx.console.print(f"  Spec: {spec_path}")
        ctx.console.print(f"  Research: {'included' if research_content else 'none'}")
        ctx.console.print(f"  Target model: {model_cfg.provider}{model_info}")
        ctx.console.print("\n[cyan][DRY RUN][/cyan] Would write:")
        ctx.console.print("  plan/plan.prompt.md")
        ctx.console.print("\n" + "=" * 60)
        ctx.console.print(plan_prompt_content)
        ctx.console.print("=" * 60)
        return

    # Write plan prompt
    prompt_path = run_dir / "plan" / "plan.prompt.md"
    prompt_path.write_text(plan_prompt_content)

    ctx.console.print("[green]Plan prompt generated[/green]")
    ctx.console.print(f"\n[bold]Spec:[/bold] {spec_path.name}")
    if research_content:
        ctx.console.print("[bold]Research:[/bold] included")
    ctx.console.print(f"[bold]Target model:[/bold] {model_cfg.provider}{model_info}")
    ctx.console.print(f"[bold]Prompt file:[/bold] {prompt_path}")
    ctx.console.print("\n" + "=" * 60)
    ctx.console.print(plan_prompt_content)
    ctx.console.print("=" * 60)
    ctx.console.print(f"\n[bold]Next step:[/bold] Copy prompt to {model_cfg.provider}, then run:")
    ctx.console.print(f"  weld plan import --run {run} --file <plan_output.md>")


def plan_import(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    file: Path = typer.Option(..., "--file", "-f", help="Plan file from Claude"),
) -> None:
    """Import Claude's plan output."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)

    if not run_dir.exists():
        ctx.console.print(f"[red]Error: Run not found: {run}[/red]")
        raise typer.Exit(1)

    if not file.exists():
        ctx.console.print(f"[red]Error: Plan file not found: {file}[/red]")
        raise typer.Exit(1)

    # Parse plan to show info in dry-run mode
    plan_content = file.read_text()
    steps, warnings = parse_steps(plan_content)

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would import plan:")
        ctx.console.print(f"  Run: {run}")
        ctx.console.print(f"  File: {file}")
        ctx.console.print(f"  Steps found: {len(steps)}")
        if warnings:
            for w in warnings:
                ctx.console.print(f"  [yellow]Warning: {w}[/yellow]")
        ctx.console.print("\n[cyan][DRY RUN][/cyan] Would write files:")
        ctx.console.print("  output.md, plan.raw.md, meta.json")
        return

    # Acquire lock for plan import
    try:
        acquire_lock(weld_dir, run, f"plan import --file {file}")
    except LockError as e:
        ctx.console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    try:
        # Write verbatim output
        (run_dir / "plan" / "output.md").write_text(plan_content)

        # Update meta with warnings
        meta_path = run_dir / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta["plan_parse_warnings"] = warnings
        meta_path.write_text(json.dumps(meta, indent=2, default=str))

        # Write normalized plan
        (run_dir / "plan" / "plan.raw.md").write_text(plan_content)

        ctx.console.print(f"[green]Imported plan with {len(steps)} steps[/green]")
        if warnings:
            for w in warnings:
                ctx.console.print(f"[yellow]Warning: {w}[/yellow]")

        ctx.console.print("\n[bold]Next step:[/bold] Review plan with Codex:")
        ctx.console.print(f"  weld plan review --run {run} --apply")
    finally:
        release_lock(weld_dir)


def plan_review(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    apply: bool = typer.Option(False, "--apply", help="Apply revised plan"),
) -> None:
    """Run Codex review on the plan."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    if not run_dir.exists():
        ctx.console.print(f"[red]Error: Run not found: {run}[/red]")
        raise typer.Exit(1)

    # Load plan
    plan_raw = run_dir / "plan" / "plan.raw.md"
    if not plan_raw.exists():
        ctx.console.print("[red]Error: No plan imported yet. Run 'weld plan import' first.[/red]")
        raise typer.Exit(1)

    # Get model config for plan review task
    model_cfg = config.get_task_model(TaskType.PLAN_REVIEW)
    model_info = f" ({model_cfg.model})" if model_cfg.model else ""

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would run plan review:")
        ctx.console.print(f"  Run: {run}")
        ctx.console.print(f"  Model: {model_cfg.provider}{model_info}")
        ctx.console.print(f"  Apply revised plan: {apply}")
        ctx.console.print("\n[cyan][DRY RUN][/cyan] Would:")
        ctx.console.print("  1. Generate Codex prompt")
        ctx.console.print("  2. Run Codex review")
        ctx.console.print("  3. Write codex.prompt.md, codex.output.md")
        if apply:
            ctx.console.print("  4. Extract and write plan.final.md")
        return

    # Acquire lock for plan review
    try:
        acquire_lock(weld_dir, run, "plan review")
    except LockError as e:
        ctx.console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    try:
        plan_content = plan_raw.read_text()

        # Generate Codex prompt
        codex_prompt = generate_codex_review_prompt(plan_content)
        (run_dir / "plan" / "codex.prompt.md").write_text(codex_prompt)

        ctx.console.print(f"[cyan]Running {model_cfg.provider} plan review{model_info}...[/cyan]")

        try:
            codex_output = run_codex(
                prompt=codex_prompt,
                exec_path=model_cfg.exec or config.codex.exec,
                sandbox=config.codex.sandbox,
                model=model_cfg.model,
                cwd=repo_root,
            )
            (run_dir / "plan" / "codex.output.md").write_text(codex_output)

            if apply:
                revised = extract_revised_plan(codex_output)
                (run_dir / "plan" / "plan.final.md").write_text(revised)
                ctx.console.print("[green]Revised plan saved to plan.final.md[/green]")

            ctx.console.print("[green]Plan review complete[/green]")
            ctx.console.print("\n[bold]Next step:[/bold] Select a step to implement:")
            ctx.console.print(f"  weld step select --run {run} --n 1")

        except CodexError as e:
            ctx.console.print(f"[red]Codex error: {e}[/red]")
            raise typer.Exit(12) from None
    finally:
        release_lock(weld_dir)
