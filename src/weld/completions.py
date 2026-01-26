"""Shell completion helpers for weld CLI."""

from pathlib import Path

from weld.config import TaskType


def complete_task_type(incomplete: str) -> list[str]:
    """Return TaskType values that start with the given prefix.

    Used for shell completion of task type arguments in CLI commands.

    Args:
        incomplete: The partial string typed by the user

    Returns:
        List of matching TaskType values (lowercase strings)
    """
    return [t.value for t in TaskType if t.value.startswith(incomplete.lower())]


def complete_export_format(incomplete: str) -> list[str]:
    """Return export format options that start with the given prefix.

    Used for shell completion of --format arguments in export commands.
    Returns toml and json always, plus yaml if pyyaml is installed.

    Args:
        incomplete: The partial string typed by the user

    Returns:
        List of matching format names, alphabetically sorted
    """
    formats = ["json", "toml"]

    # Add yaml if pyyaml is available
    try:
        import yaml  # noqa: F401

        formats.append("yaml")
    except ImportError:
        pass

    # Sort alphabetically and filter by prefix
    return sorted(f for f in formats if f.startswith(incomplete.lower()))


def complete_markdown_file(incomplete: str) -> list[str]:
    """Return markdown files and directories matching the given path prefix.

    Used for shell completion of markdown file arguments in CLI commands.
    Provides file system path completion filtered to .md files only.

    Args:
        incomplete: The partial path typed by the user (may be empty)

    Returns:
        List of matching paths, alphabetically sorted, capped at 20 results.
        Directories include a trailing slash to indicate they can be expanded.
    """
    max_results = 20

    # Handle empty input - start from current directory
    if not incomplete:
        search_dir = Path(".")
        prefix = ""
    else:
        path = Path(incomplete)
        # If the incomplete path ends with /, list contents of that directory
        if incomplete.endswith("/") or incomplete.endswith("\\"):
            search_dir = path
            prefix = ""
        # Otherwise, search in the parent directory for matches
        elif path.is_dir():
            # User typed a directory name without trailing slash
            search_dir = path
            prefix = ""
        else:
            search_dir = path.parent if path.parent != path else Path(".")
            prefix = path.name

    results: list[str] = []

    try:
        if not search_dir.exists() or not search_dir.is_dir():
            return []

        for entry in search_dir.iterdir():
            # Skip hidden files
            if entry.name.startswith("."):
                continue

            # Check if name matches prefix
            if prefix and not entry.name.lower().startswith(prefix.lower()):
                continue

            try:
                if entry.is_dir():
                    # Add directories with trailing slash
                    results.append(str(entry) + "/")
                elif entry.is_file() and entry.suffix.lower() == ".md":
                    # Add markdown files
                    results.append(str(entry))
            except PermissionError:
                # Skip entries we can't access
                continue

    except PermissionError:
        # Can't read directory, return empty
        return []

    # Sort alphabetically and cap at max_results
    return sorted(results)[:max_results]


def complete_step_number(incomplete: str) -> list[str]:
    """Return step numbers that start with the given prefix.

    Used for shell completion of step number arguments in CLI commands.
    Returns static step numbers 1.1-3.3 as fallback suggestions when
    dynamic plan parsing is not available.

    Args:
        incomplete: The partial string typed by the user

    Returns:
        List of matching step numbers in format "X.Y"
    """
    # Static fallback step numbers covering 3 phases with 3 steps each
    step_numbers = [
        "1.1",
        "1.2",
        "1.3",
        "2.1",
        "2.2",
        "2.3",
        "3.1",
        "3.2",
        "3.3",
    ]

    return [s for s in step_numbers if s.startswith(incomplete)]


def complete_phase_number(incomplete: str) -> list[str]:
    """Return phase numbers that start with the given prefix.

    Used for shell completion of phase number arguments in CLI commands.
    Returns static phase numbers 1-5 as suggestions.

    Args:
        incomplete: The partial string typed by the user

    Returns:
        List of matching phase numbers as strings
    """
    phase_numbers = ["1", "2", "3", "4", "5"]

    return [p for p in phase_numbers if p.startswith(incomplete)]


# ============================================================================
# Auto-install shell completions
# ============================================================================

# Marker comment used to identify weld completion lines in shell RC files
_COMPLETION_MARKER = "# weld shell completion (auto-installed)"


def get_completion_marker_path() -> Path:
    """Return path to marker file tracking completion installation.

    The marker file is stored in ~/.local/share/weld/ following XDG conventions
    for application data that should persist across sessions.

    Returns:
        Path to the completion_installed marker file
    """
    return Path.home() / ".local" / "share" / "weld" / "completion_installed"


def is_completion_installed() -> bool:
    """Check if completions have been auto-installed.

    Returns:
        True if the marker file exists, indicating completions are installed
    """
    return get_completion_marker_path().exists()


def mark_completion_installed(shell: str) -> None:
    """Create marker file indicating completions are installed.

    Args:
        shell: Name of the shell completions were installed for (bash, zsh, fish)
    """
    marker = get_completion_marker_path()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{shell}\n")


def detect_shell() -> str | None:
    """Detect current shell from SHELL environment variable.

    Returns:
        Shell name (bash, zsh, or fish) if supported, None otherwise
    """
    import os

    shell_path = os.environ.get("SHELL", "")
    if not shell_path:
        return None
    shell_name = shell_path.split("/")[-1]
    return shell_name if shell_name in ("bash", "zsh", "fish") else None


def _get_rc_file_path(shell: str) -> Path | None:
    """Get the RC file path for the given shell.

    Args:
        shell: Shell name (bash, zsh, or fish)

    Returns:
        Path to the shell's RC file, or None if unsupported
    """
    home = Path.home()
    if shell == "bash":
        return home / ".bashrc"
    elif shell == "zsh":
        return home / ".zshrc"
    elif shell == "fish":
        return home / ".config" / "fish" / "completions" / "weld.fish"
    return None


def _get_completion_script(shell: str) -> str | None:
    """Generate the completion script for the given shell.

    Uses Typer's built-in completion generation via the _COMPLETE environment
    variable mechanism.

    Args:
        shell: Shell name (bash, zsh, or fish)

    Returns:
        Completion script content, or None if generation fails
    """
    import subprocess

    # Map shell names to Typer's completion source format
    shell_to_source = {
        "bash": "bash_source",
        "zsh": "zsh_source",
        "fish": "fish_source",
    }

    source_type = shell_to_source.get(shell)
    if not source_type:
        return None

    try:
        # Run weld with _WELD_COMPLETE env var to get completion script
        result = subprocess.run(
            ["weld"],
            env={**__import__("os").environ, "_WELD_COMPLETE": source_type},
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return None


def _completion_already_in_rc(rc_path: Path) -> bool:
    """Check if weld completion is already configured in the RC file.

    Args:
        rc_path: Path to the shell RC file

    Returns:
        True if completion marker is found in the file
    """
    if not rc_path.exists():
        return False
    try:
        content = rc_path.read_text()
        return _COMPLETION_MARKER in content or "weld" in content.lower()
    except OSError:
        return False


def _install_completion_to_rc(shell: str, rc_path: Path, script: str) -> bool:
    """Install completion script to the shell RC file.

    For fish shell, writes to a dedicated completion file.
    For bash/zsh, appends to the RC file.

    Args:
        shell: Shell name
        rc_path: Path to the RC file or completion file
        script: Completion script content

    Returns:
        True if installation succeeded
    """
    try:
        if shell == "fish":
            # Fish uses dedicated completion files
            rc_path.parent.mkdir(parents=True, exist_ok=True)
            rc_path.write_text(f"{_COMPLETION_MARKER}\n{script}")
        else:
            # Bash/Zsh: append to RC file
            with rc_path.open("a") as f:
                f.write(f"\n{_COMPLETION_MARKER}\n{script}\n")
        return True
    except OSError:
        return False


def auto_install_completion() -> tuple[bool, str]:
    """Auto-install shell completions on first run.

    Checks if completions are already installed (via marker file), and if not,
    detects the shell, generates the completion script, and installs it to
    the appropriate RC file.

    Returns:
        Tuple of (success: bool, message: str).
        - If already installed: (True, "")
        - If successfully installed: (True, user message about restarting shell)
        - If installation failed: (False, "")
    """
    # Already installed - no message needed
    if is_completion_installed():
        return True, ""

    # Detect shell
    shell = detect_shell()
    if not shell:
        return False, ""

    # Get RC file path
    rc_path = _get_rc_file_path(shell)
    if not rc_path:
        return False, ""

    # Check if already configured (user may have manually installed)
    if _completion_already_in_rc(rc_path):
        mark_completion_installed(shell)
        return True, ""

    # Generate completion script
    script = _get_completion_script(shell)
    if not script:
        return False, ""

    # Install to RC file
    if not _install_completion_to_rc(shell, rc_path, script):
        return False, ""

    # Mark as installed
    mark_completion_installed(shell)

    # Return success message
    if shell == "fish":
        return True, "Shell completions installed for weld."
    else:
        msg = f"Shell completions installed. Restart your shell or run: source ~/{rc_path.name}"
        return True, msg
