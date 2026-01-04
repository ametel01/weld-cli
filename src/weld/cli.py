"""Weld CLI: Human-in-the-loop coding harness."""

import json
import re
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from weld import __version__

from .codex import CodexError, extract_revised_plan, run_codex
from .config import TaskType, load_config, write_config_template
from .constants import INIT_TOOL_CHECK_TIMEOUT
from .git import GitError, get_repo_root
from .logging import configure_logging
from .models import Status, Step
from .output import OutputContext
from .run import (
    create_meta,
    create_run_directory,
    create_spec_ref,
    generate_run_id,
    get_run_dir,
    get_weld_dir,
    list_runs,
)


def _version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"weld {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="weld",
    help="Human-in-the-loop coding harness with transcript provenance",
    no_args_is_help=True,
)

# Sub-commands
plan_app = typer.Typer(help="Plan management commands")
step_app = typer.Typer(help="Step implementation commands")
transcript_app = typer.Typer(help="Transcript management commands")

app.add_typer(plan_app, name="plan")
app.add_typer(step_app, name="step")
app.add_typer(transcript_app, name="transcript")

console = Console()

# Global output context
_ctx: OutputContext | None = None


def get_output_context() -> OutputContext:
    """Get the current output context."""
    if _ctx is None:
        return OutputContext(Console())
    return _ctx


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    verbose: int = typer.Option(
        0,
        "--verbose",
        "-v",
        count=True,
        help="Increase verbosity (-v, -vv)",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress non-error output",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output in JSON format for automation",
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable colored output",
    ),
) -> None:
    """Weld CLI - Human-in-the-loop coding harness."""
    global _ctx
    global console
    console = configure_logging(
        verbosity=verbose,
        quiet=quiet,
        no_color=no_color,
    )
    _ctx = OutputContext(console=console, json_mode=json_output)


# ============================================================================
# weld init
# ============================================================================


@app.command()
def init() -> None:
    """Initialize weld in the current repository."""
    # Check git repo
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = repo_root / ".weld"

    # Create directories
    weld_dir.mkdir(exist_ok=True)
    (weld_dir / "runs").mkdir(exist_ok=True)

    # Create config if missing
    config_path = weld_dir / "config.toml"
    if not config_path.exists():
        write_config_template(weld_dir)
        console.print(f"[green]Created config template:[/green] {config_path}")
    else:
        console.print(f"[yellow]Config already exists:[/yellow] {config_path}")

    # Validate toolchain
    tools = {
        "git": ["git", "--version"],
        "gh": ["gh", "auth", "status"],
        "codex": ["codex", "--version"],
        "claude-code-transcripts": ["claude-code-transcripts", "--help"],
    }

    all_ok = True
    for name, cmd in tools.items():
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=INIT_TOOL_CHECK_TIMEOUT
            )
            if result.returncode == 0:
                console.print(f"[green]✓[/green] {name}")
            else:
                console.print(f"[red]✗[/red] {name}: {result.stderr.strip()[:50]}")
                all_ok = False
        except FileNotFoundError:
            console.print(f"[red]✗[/red] {name}: not found in PATH")
            all_ok = False
        except subprocess.TimeoutExpired:
            console.print(f"[yellow]?[/yellow] {name}: timed out")

    if not all_ok:
        console.print("\n[yellow]Warning: Some tools are missing or not configured[/yellow]")
        raise typer.Exit(2)

    console.print("\n[bold green]Weld initialized successfully![/bold green]")


# ============================================================================
# weld run start
# ============================================================================


@app.command("run")
def run_start(
    spec: Path = typer.Option(..., "--spec", "-s", help="Path to spec file"),
    name: str | None = typer.Option(None, "--name", "-n", help="Run name slug"),
) -> None:
    """Start a new weld run."""
    # Validate spec exists
    if not spec.exists():
        console.print(f"[red]Error: Spec file not found: {spec}[/red]")
        raise typer.Exit(1)

    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    if not weld_dir.exists():
        console.print("[red]Error: Weld not initialized. Run 'weld init' first.[/red]")
        raise typer.Exit(1)

    config = load_config(weld_dir)

    # Generate run ID
    run_id = generate_run_id(slug=name, spec_path=spec)
    run_dir = create_run_directory(weld_dir, run_id)

    # Create metadata
    meta = create_meta(run_id, repo_root, config)
    (run_dir / "meta.json").write_text(meta.model_dump_json(indent=2))

    # Create spec reference
    spec_ref = create_spec_ref(spec)
    (run_dir / "inputs" / "spec.ref.json").write_text(spec_ref.model_dump_json(indent=2))

    # Generate plan prompt
    from .plan import generate_plan_prompt

    spec_content = spec.read_text()
    plan_prompt = generate_plan_prompt(spec_content, spec)

    # Get configured model for plan generation
    model_cfg = config.get_task_model(TaskType.PLAN_GENERATION)
    model_info = f" ({model_cfg.model})" if model_cfg.model else ""

    prompt_path = run_dir / "plan" / "plan.prompt.md"
    prompt_path.write_text(plan_prompt)

    # Output
    console.print(Panel(f"[bold]Run created:[/bold] {run_id}", style="green"))
    console.print(f"\n[bold]Target model:[/bold] {model_cfg.provider}{model_info}")
    console.print(f"[bold]Prompt file:[/bold] {prompt_path}")
    console.print("\n" + "=" * 60)
    console.print(plan_prompt)
    console.print("=" * 60)
    console.print(f"\n[bold]Next step:[/bold] Copy prompt to {model_cfg.provider}, then run:")
    console.print(f"  weld plan import --run {run_id} --file <plan_output.md>")


# ============================================================================
# weld plan import
# ============================================================================


@plan_app.command("import")
def plan_import(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    file: Path = typer.Option(..., "--file", "-f", help="Plan file from Claude"),
) -> None:
    """Import Claude's plan output."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)

    if not run_dir.exists():
        console.print(f"[red]Error: Run not found: {run}[/red]")
        raise typer.Exit(1)

    if not file.exists():
        console.print(f"[red]Error: Plan file not found: {file}[/red]")
        raise typer.Exit(1)

    plan_content = file.read_text()

    # Write verbatim output
    (run_dir / "plan" / "claude.output.md").write_text(plan_content)

    # Parse and validate
    from .plan import parse_steps

    steps, warnings = parse_steps(plan_content)

    # Update meta with warnings
    meta_path = run_dir / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["plan_parse_warnings"] = warnings
    meta_path.write_text(json.dumps(meta, indent=2, default=str))

    # Write normalized plan
    (run_dir / "plan" / "plan.raw.md").write_text(plan_content)

    console.print(f"[green]Imported plan with {len(steps)} steps[/green]")
    if warnings:
        for w in warnings:
            console.print(f"[yellow]Warning: {w}[/yellow]")

    console.print("\n[bold]Next step:[/bold] Review plan with Codex:")
    console.print(f"  weld plan review --run {run} --apply")


# ============================================================================
# weld plan review
# ============================================================================


@plan_app.command("review")
def plan_review(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    apply: bool = typer.Option(False, "--apply", help="Apply revised plan"),
) -> None:
    """Run Codex review on the plan."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    if not run_dir.exists():
        console.print(f"[red]Error: Run not found: {run}[/red]")
        raise typer.Exit(1)

    # Load plan
    plan_raw = run_dir / "plan" / "plan.raw.md"
    if not plan_raw.exists():
        console.print("[red]Error: No plan imported yet. Run 'weld plan import' first.[/red]")
        raise typer.Exit(1)

    plan_content = plan_raw.read_text()

    # Generate Codex prompt
    from .plan import generate_codex_review_prompt

    codex_prompt = generate_codex_review_prompt(plan_content)
    (run_dir / "plan" / "codex.prompt.md").write_text(codex_prompt)

    # Get model config for plan review task
    model_cfg = config.get_task_model(TaskType.PLAN_REVIEW)
    model_info = f" ({model_cfg.model})" if model_cfg.model else ""
    console.print(f"[cyan]Running {model_cfg.provider} plan review{model_info}...[/cyan]")

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
            console.print("[green]Revised plan saved to plan.final.md[/green]")

        console.print("[green]Plan review complete[/green]")
        console.print("\n[bold]Next step:[/bold] Select a step to implement:")
        console.print(f"  weld step select --run {run} --n 1")

    except CodexError as e:
        console.print(f"[red]Codex error: {e}[/red]")
        raise typer.Exit(12) from None


# ============================================================================
# weld step select
# ============================================================================


@step_app.command("select")
def step_select(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
) -> None:
    """Select a step from the plan."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Find plan file
    plan_final = run_dir / "plan" / "plan.final.md"
    plan_raw = run_dir / "plan" / "plan.raw.md"
    plan_path = plan_final if plan_final.exists() else plan_raw

    if not plan_path.exists():
        console.print("[red]Error: No plan found[/red]")
        raise typer.Exit(1)

    # Parse steps
    from .plan import parse_steps

    steps, _ = parse_steps(plan_path.read_text())

    # Find requested step
    step = next((s for s in steps if s.n == n), None)
    if not step:
        console.print(f"[red]Error: Step {n} not found. Available: {[s.n for s in steps]}[/red]")
        raise typer.Exit(1)

    # Create step directory
    from .step import create_step_directory, generate_impl_prompt

    step_dir = create_step_directory(run_dir, step)

    # Write step.json
    (step_dir / "step.json").write_text(step.model_dump_json(indent=2))

    # Generate implementation prompt
    impl_prompt = generate_impl_prompt(step, config.checks.command)
    prompt_path = step_dir / "prompt" / "impl.prompt.md"
    prompt_path.write_text(impl_prompt)

    # Get configured model for implementation
    model_cfg = config.get_task_model(TaskType.IMPLEMENTATION)
    model_info = f" ({model_cfg.model})" if model_cfg.model else ""

    console.print(f"[green]Selected step {n}: {step.title}[/green]")
    console.print(f"\n[bold]Target model:[/bold] {model_cfg.provider}{model_info}")
    console.print(f"[bold]Prompt file:[/bold] {prompt_path}")
    console.print("\n" + "=" * 60)
    console.print(impl_prompt)
    console.print("=" * 60)
    console.print("\n[bold]Next step:[/bold] Start implementation loop:")
    console.print(f"  weld step loop --run {run} --n {n} --wait")


# ============================================================================
# weld step snapshot
# ============================================================================


@step_app.command("snapshot")
def step_snapshot(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    iter: int = typer.Option(1, "--iter", "-i", help="Iteration number"),
) -> None:
    """Capture current diff and checks for a step iteration."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Find step directory
    steps_dir = run_dir / "steps"
    step_dirs = [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]

    if not step_dirs:
        console.print(f"[red]Error: Step {n} not selected yet[/red]")
        raise typer.Exit(1)

    step_dir = step_dirs[0]

    # Create iteration directory
    from .step import create_iter_directory

    iter_dir = create_iter_directory(step_dir, iter)

    # Capture diff
    from .diff import capture_diff, write_diff

    diff, nonempty = capture_diff(repo_root)
    write_diff(iter_dir / "diff.patch", diff)

    if not nonempty:
        console.print("[yellow]No changes detected[/yellow]")
        status = Status.model_validate(
            {
                "pass": False,
                "checks_exit_code": -1,
                "diff_nonempty": False,
            }
        )
        (iter_dir / "status.json").write_text(status.model_dump_json(by_alias=True, indent=2))
        raise typer.Exit(0)

    # Run checks
    from .checks import run_checks, write_checks

    console.print("[cyan]Running checks...[/cyan]")
    checks_output, exit_code = run_checks(config.checks.command, repo_root)
    write_checks(iter_dir / "checks.txt", checks_output)

    console.print(f"[green]Snapshot captured for iteration {iter}[/green]")
    console.print(f"  Diff: {len(diff)} bytes")
    console.print(f"  Checks exit code: {exit_code}")


# ============================================================================
# weld step review
# ============================================================================


@step_app.command("review")
def step_review_cmd(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    iter: int = typer.Option(1, "--iter", "-i", help="Iteration number"),
) -> None:
    """Run Codex review on step implementation."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Find step
    steps_dir = run_dir / "steps"
    step_dirs = [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]

    if not step_dirs:
        console.print(f"[red]Error: Step {n} not found[/red]")
        raise typer.Exit(1)

    step_dir = step_dirs[0]
    iter_dir = step_dir / "iter" / f"{iter:02d}"

    # Load step
    step = Step.model_validate(json.loads((step_dir / "step.json").read_text()))

    # Load diff and checks
    diff = (iter_dir / "diff.patch").read_text() if (iter_dir / "diff.patch").exists() else ""
    checks = (iter_dir / "checks.txt").read_text() if (iter_dir / "checks.txt").exists() else ""

    # Parse checks exit code
    exit_match = re.search(r"exit_code:\s*(\d+)", checks)
    checks_exit = int(exit_match.group(1)) if exit_match else -1

    # Run review
    from .review import run_step_review

    console.print("[cyan]Running Codex review...[/cyan]")

    review_md, issues, status = run_step_review(
        step=step,
        diff=diff,
        checks_output=checks,
        checks_exit_code=checks_exit,
        config=config,
        cwd=repo_root,
    )

    # Write results
    (iter_dir / "codex.review.md").write_text(review_md)
    (iter_dir / "codex.issues.json").write_text(issues.model_dump_json(by_alias=True, indent=2))
    (iter_dir / "status.json").write_text(status.model_dump_json(by_alias=True, indent=2))

    if status.pass_:
        console.print("[bold green]Review passed![/bold green]")
    else:
        console.print(
            f"[red]Review found {status.issue_count} issues ({status.blocker_count} blockers)[/red]"
        )


# ============================================================================
# weld step fix-prompt
# ============================================================================


@step_app.command("fix-prompt")
def step_fix_prompt(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    iter: int = typer.Option(..., "--iter", "-i", help="Current iteration"),
) -> None:
    """Generate fix prompt for next iteration."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)

    # Find step
    steps_dir = run_dir / "steps"
    step_dirs = [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]

    if not step_dirs:
        console.print(f"[red]Error: Step {n} not found[/red]")
        raise typer.Exit(1)

    step_dir = step_dirs[0]
    iter_dir = step_dir / "iter" / f"{iter:02d}"

    # Load step and issues
    from .step import generate_fix_prompt

    step = Step.model_validate(json.loads((step_dir / "step.json").read_text()))
    issues = json.loads((iter_dir / "codex.issues.json").read_text())

    # Generate fix prompt
    config = load_config(weld_dir)
    model_cfg = config.get_task_model(TaskType.FIX_GENERATION)
    model_info = f" ({model_cfg.model})" if model_cfg.model else ""

    fix_prompt = generate_fix_prompt(step, issues, iter)
    fix_path = step_dir / "prompt" / f"fix.prompt.iter{iter + 1:02d}.md"
    fix_path.write_text(fix_prompt)

    console.print(f"[green]Fix prompt written to:[/green] {fix_path}")
    console.print(f"[bold]Target model:[/bold] {model_cfg.provider}{model_info}")
    console.print("\n" + "=" * 60)
    console.print(fix_prompt)
    console.print("=" * 60)


# ============================================================================
# weld step loop
# ============================================================================


@step_app.command("loop")
def step_loop(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    max: int | None = typer.Option(None, "--max", "-m", help="Max iterations"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for user between iterations"),
) -> None:
    """Run implement-review-fix loop for a step."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Find or select step
    steps_dir = run_dir / "steps"
    step_dirs = (
        [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]
        if steps_dir.exists()
        else []
    )

    if not step_dirs:
        # Auto-select step
        console.print(f"[yellow]Step {n} not selected, selecting now...[/yellow]")
        step_select(run=run, n=n)
        step_dirs = [
            d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")
        ]

    step_dir = step_dirs[0]

    # Load step
    step = Step.model_validate(json.loads((step_dir / "step.json").read_text()))

    # Print initial prompt with model info
    impl_model_cfg = config.get_task_model(TaskType.IMPLEMENTATION)
    impl_model_info = f" ({impl_model_cfg.model})" if impl_model_cfg.model else ""
    review_model_cfg = config.get_task_model(TaskType.IMPLEMENTATION_REVIEW)
    review_model_info = f" ({review_model_cfg.model})" if review_model_cfg.model else ""

    impl_prompt_path = step_dir / "prompt" / "impl.prompt.md"
    console.print(
        f"\n[bold]Implementation model:[/bold] {impl_model_cfg.provider}{impl_model_info}"
    )
    console.print(f"[bold]Review model:[/bold] {review_model_cfg.provider}{review_model_info}")
    console.print(f"[bold]Implementation prompt:[/bold] {impl_prompt_path}")
    console.print("\n" + "=" * 60)
    console.print(impl_prompt_path.read_text())
    console.print("=" * 60 + "\n")

    # Run loop
    from .loop import run_step_loop

    result = run_step_loop(
        run_dir=run_dir,
        step=step,
        config=config,
        repo_root=repo_root,
        max_iterations=max,
        wait_mode=wait,
    )

    if result.success:
        console.print(
            f"\n[bold green]Step {n} completed in {result.iterations} iteration(s)![/bold green]"
        )
        console.print("\n[bold]Next step:[/bold] Commit your changes:")
        console.print(f"  weld commit --run {run} -m 'Implement step {n}' --staged")
        raise typer.Exit(0)
    else:
        console.print(
            f"\n[bold red]Step {n} did not pass after {result.iterations} iterations[/bold red]"
        )
        raise typer.Exit(10)


# ============================================================================
# weld transcript gist
# ============================================================================


@transcript_app.command("gist")
def transcript_gist(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
) -> None:
    """Generate transcript gist."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    from .commit import ensure_transcript_gist

    console.print("[cyan]Generating transcript gist...[/cyan]")
    result = ensure_transcript_gist(run_dir, config, repo_root)

    if result.gist_url:
        console.print(f"[green]Gist URL:[/green] {result.gist_url}")
        if result.preview_url:
            console.print(f"[green]Preview:[/green] {result.preview_url}")
    else:
        console.print("[red]Failed to generate gist[/red]")
        raise typer.Exit(21)

    if result.warnings:
        for w in result.warnings:
            console.print(f"[yellow]Warning: {w}[/yellow]")


# ============================================================================
# weld commit
# ============================================================================


@app.command()
def commit(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    message: str = typer.Option(..., "-m", help="Commit message"),
    all: bool = typer.Option(False, "--all", "-a", help="Stage all changes"),
    staged: bool = typer.Option(True, "--staged", help="Commit staged changes only"),
) -> None:
    """Create commit with transcript trailer."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    if not run_dir.exists():
        console.print(f"[red]Error: Run not found: {run}[/red]")
        raise typer.Exit(1)

    from .commit import CommitError, do_commit

    try:
        sha = do_commit(
            run_dir=run_dir,
            message=message,
            config=config,
            repo_root=repo_root,
            stage_all_changes=all,
        )
        console.print(f"[bold green]Committed:[/bold green] {sha[:8]}")
    except CommitError as e:
        if "No staged changes" in str(e):
            console.print("[red]Error: No staged changes to commit[/red]")
            raise typer.Exit(20) from None
        elif "gist" in str(e).lower():
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(21) from None
        else:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(22) from None


# ============================================================================
# weld list (helper command)
# ============================================================================


@app.command("list")
def list_runs_cmd() -> None:
    """List all runs."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    runs = list_runs(weld_dir)

    if not runs:
        console.print("[yellow]No runs found[/yellow]")
        return

    console.print("[bold]Runs:[/bold]")
    for r in runs:
        console.print(f"  {r}")


if __name__ == "__main__":
    app()
