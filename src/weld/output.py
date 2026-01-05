"""Output formatting for weld CLI."""

import json
from dataclasses import dataclass
from typing import Any

from rich.console import Console


@dataclass
class OutputContext:
    """Context for output formatting."""

    console: Console
    json_mode: bool = False
    dry_run: bool = False

    def print(self, message: str, style: str | None = None) -> None:
        """Print message respecting output mode."""
        if not self.json_mode:
            self.console.print(message, style=style)

    def print_json(self, data: dict[str, Any]) -> None:
        """Print JSON data."""
        if self.json_mode:
            print(json.dumps(data, indent=2, default=str))

    def result(self, data: dict[str, Any], message: str = "") -> None:
        """Print result in appropriate format."""
        if self.json_mode:
            self.print_json(data)
        elif message:
            self.console.print(message)

    def error(self, message: str, data: dict[str, Any] | None = None) -> None:
        """Print error in appropriate format."""
        if self.json_mode and data:
            self.print_json({"error": message, **data})
        elif self.json_mode:
            self.print_json({"error": message})
        else:
            self.console.print(f"[red]Error: {message}[/red]")

    def success(self, message: str, data: dict[str, Any] | None = None) -> None:
        """Print success message in appropriate format."""
        if self.json_mode and data:
            self.print_json({"success": message, **data})
        elif self.json_mode:
            self.print_json({"success": message})
        else:
            self.console.print(f"[green]{message}[/green]")


# Global output context (set by cli.py main callback)
_ctx: OutputContext | None = None


def get_output_context() -> OutputContext:
    """Get the current output context.

    Returns a default OutputContext if not yet initialized by CLI.
    """
    if _ctx is None:
        return OutputContext(Console())
    return _ctx


def set_output_context(ctx: OutputContext) -> None:
    """Set the global output context. Called by CLI main callback."""
    global _ctx
    _ctx = ctx
