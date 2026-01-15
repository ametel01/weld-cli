"""Input validation utilities for CLI commands.

Provides early validation of file paths with helpful error messages.
All validation functions return error strings on failure, None on success.
"""

from pathlib import Path


def validate_input_file(
    path: Path,
    *,
    must_be_markdown: bool = False,
    param_name: str = "input file",
) -> tuple[str, str | None] | None:
    """Validate an input file path.

    Args:
        path: Path to validate
        must_be_markdown: If True, require .md extension
        param_name: Parameter name for error messages

    Returns:
        None if valid, or (error_message, hint) tuple if invalid
    """
    if not path.exists():
        return (
            f"{param_name.capitalize()} not found: {path}",
            f"Check the path exists: ls {path.parent}",
        )

    if path.is_dir():
        return (
            f"{param_name.capitalize()} is a directory, expected a file: {path}",
            f"Provide a file path, e.g.: {path}/example.md",
        )

    if must_be_markdown and path.suffix.lower() != ".md":
        return (
            f"{param_name.capitalize()} should be a markdown file (.md): {path}",
            f"Rename or create a .md file: {path.with_suffix('.md')}",
        )

    return None


def validate_output_path(
    path: Path,
    *,
    must_be_markdown: bool = False,
    param_name: str = "output",
) -> tuple[str, str | None] | None:
    """Validate an output file path.

    Args:
        path: Path to validate
        must_be_markdown: If True, require .md extension
        param_name: Parameter name for error messages

    Returns:
        None if valid, or (error_message, hint) tuple if invalid
    """
    # Check if path is an existing directory
    if path.exists() and path.is_dir():
        suggested_file = path / "output.md"
        return (
            f"{param_name.capitalize()} path is a directory, expected a file: {path}",
            f"Provide a file path: --output {suggested_file}",
        )

    # Check extension if required
    if must_be_markdown and path.suffix.lower() != ".md":
        corrected = path.with_suffix(".md")
        return (
            f"{param_name.capitalize()} should be a markdown file (.md): {path}",
            f"Use .md extension: --output {corrected}",
        )

    # Check parent directory exists or can be created
    parent = path.parent
    if parent and not parent.exists():
        # Check if any ancestor exists (we can create intermediate dirs)
        existing_ancestor = parent
        while existing_ancestor and not existing_ancestor.exists():
            existing_ancestor = existing_ancestor.parent

        if existing_ancestor is None or not existing_ancestor.exists():
            return (
                f"Parent directory does not exist: {parent}",
                f"Create the directory first: mkdir -p {parent}",
            )

    return None


def validate_plan_file(
    path: Path,
    param_name: str = "plan file",
) -> tuple[str, str | None] | None:
    """Validate a plan file path.

    Args:
        path: Path to validate
        param_name: Parameter name for error messages

    Returns:
        None if valid, or (error_message, hint) tuple if invalid
    """
    if not path.exists():
        return (
            f"{param_name.capitalize()} not found: {path}",
            f"Check the path exists: ls {path.parent}",
        )

    if path.is_dir():
        # Look for .md files in the directory
        md_files = list(path.glob("*.md"))
        if md_files:
            suggestion = md_files[0]
            hint = f"Did you mean: {suggestion}"
        else:
            hint = f"Provide a file path, not a directory: {path}/plan.md"
        return (
            f"{param_name.capitalize()} is a directory, expected a markdown file: {path}",
            hint,
        )

    if path.suffix.lower() != ".md":
        return (
            f"{param_name.capitalize()} should be a markdown file (.md): {path}",
            "Plans must be markdown files ending in .md",
        )

    return None
