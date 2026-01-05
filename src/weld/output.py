"""Output formatting for weld CLI."""

import json
from dataclasses import dataclass
from typing import Any

from rich.console import Console

# JSON output schema version for automation compatibility
SCHEMA_VERSION = 1


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
        """Print JSON data with schema version wrapper."""
        if self.json_mode:
            wrapped = {
                "schema_version": SCHEMA_VERSION,
                "data": data,
            }
            print(json.dumps(wrapped, indent=2, default=str))

    def result(self, data: dict[str, Any], message: str = "") -> None:
        """Print result in appropriate format."""
        if self.json_mode:
            self.print_json(data)
        elif message:
            self.console.print(message)

    def error(
        self,
        message: str,
        data: dict[str, Any] | None = None,
        next_action: str | None = None,
    ) -> None:
        """Print error with optional suggested next action.

        Args:
            message: Error message to display
            data: Optional structured data for JSON mode
            next_action: Optional command suggestion for recovery
        """
        if self.json_mode:
            error_data: dict[str, Any] = {"error": message}
            if data:
                error_data.update(data)
            if next_action:
                error_data["next_action"] = next_action
            self.print_json(error_data)
        else:
            self.console.print(f"[red]Error: {message}[/red]")
            if next_action:
                self.console.print(f"  Run: [bold]{next_action}[/bold]")

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
