"""Tests for output formatting."""

import io
import json

from rich.console import Console

from weld.output import SCHEMA_VERSION, OutputContext


class TestOutputContextPrint:
    """Tests for OutputContext.print method."""

    def test_print_in_normal_mode(self) -> None:
        """print should output message in normal mode."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        ctx = OutputContext(console=console, json_mode=False)

        ctx.print("Hello world")
        console.file.seek(0)
        assert "Hello world" in output.getvalue()

    def test_print_suppressed_in_json_mode(self) -> None:
        """print should be suppressed in json mode."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        ctx = OutputContext(console=console, json_mode=True)

        ctx.print("Hello world")
        console.file.seek(0)
        assert output.getvalue() == ""

    def test_print_with_style(self) -> None:
        """print should accept style parameter."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        ctx = OutputContext(console=console, json_mode=False)

        ctx.print("Styled message", style="bold")
        console.file.seek(0)
        assert "Styled message" in output.getvalue()


class TestOutputContextPrintJson:
    """Tests for OutputContext.print_json method."""

    def test_print_json_in_json_mode(self, capsys) -> None:
        """print_json should output JSON with schema version wrapper."""
        console = Console()
        ctx = OutputContext(console=console, json_mode=True)

        ctx.print_json({"key": "value", "number": 42})
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["schema_version"] == SCHEMA_VERSION
        assert output["data"]["key"] == "value"
        assert output["data"]["number"] == 42

    def test_print_json_suppressed_in_normal_mode(self, capsys) -> None:
        """print_json should be suppressed in normal mode."""
        console = Console()
        ctx = OutputContext(console=console, json_mode=False)

        ctx.print_json({"key": "value"})
        captured = capsys.readouterr()
        assert captured.out == ""


class TestOutputContextResult:
    """Tests for OutputContext.result method."""

    def test_result_prints_json_in_json_mode(self, capsys) -> None:
        """result should output JSON data with schema version wrapper."""
        console = Console()
        ctx = OutputContext(console=console, json_mode=True)

        ctx.result({"status": "ok"}, "Success message")
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["schema_version"] == SCHEMA_VERSION
        assert output["data"]["status"] == "ok"

    def test_result_prints_message_in_normal_mode(self) -> None:
        """result should output message in normal mode."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        ctx = OutputContext(console=console, json_mode=False)

        ctx.result({"status": "ok"}, "Success message")
        console.file.seek(0)
        assert "Success message" in output.getvalue()

    def test_result_no_output_without_message(self) -> None:
        """result should not output if no message in normal mode."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        ctx = OutputContext(console=console, json_mode=False)

        ctx.result({"status": "ok"})
        console.file.seek(0)
        assert output.getvalue() == ""


class TestOutputContextError:
    """Tests for OutputContext.error method."""

    def test_error_prints_json_in_json_mode(self, capsys) -> None:
        """error should output JSON with schema version wrapper."""
        console = Console()
        ctx = OutputContext(console=console, json_mode=True)

        ctx.error("Something failed", {"code": 500})
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["schema_version"] == SCHEMA_VERSION
        assert output["data"]["error"] == "Something failed"
        assert output["data"]["code"] == 500

    def test_error_prints_message_in_normal_mode(self) -> None:
        """error should output formatted message in normal mode."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        ctx = OutputContext(console=console, json_mode=False)

        ctx.error("Something failed")
        console.file.seek(0)
        assert "Something failed" in output.getvalue()

    def test_error_without_data_in_json_mode(self, capsys) -> None:
        """error without data should output JSON with schema version wrapper."""
        console = Console()
        ctx = OutputContext(console=console, json_mode=True)

        ctx.error("Something failed", data=None)
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["schema_version"] == SCHEMA_VERSION
        assert output["data"]["error"] == "Something failed"


class TestOutputContextSuccess:
    """Tests for OutputContext.success method."""

    def test_success_prints_json_in_json_mode_with_data(self, capsys) -> None:
        """success should output JSON with schema version wrapper."""
        console = Console()
        ctx = OutputContext(console=console, json_mode=True)

        ctx.success("Operation completed", {"count": 5})
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["schema_version"] == SCHEMA_VERSION
        assert output["data"]["success"] == "Operation completed"
        assert output["data"]["count"] == 5

    def test_success_prints_json_in_json_mode_without_data(self, capsys) -> None:
        """success should output JSON with schema version wrapper even without data."""
        console = Console()
        ctx = OutputContext(console=console, json_mode=True)

        ctx.success("All done")
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["schema_version"] == SCHEMA_VERSION
        assert output["data"]["success"] == "All done"

    def test_success_prints_message_in_normal_mode(self) -> None:
        """success should output formatted message in normal mode."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        ctx = OutputContext(console=console, json_mode=False)

        ctx.success("Task completed")
        console.file.seek(0)
        assert "Task completed" in output.getvalue()

    def test_success_ignores_data_in_normal_mode(self) -> None:
        """success should only show message in normal mode, not data."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        ctx = OutputContext(console=console, json_mode=False)

        ctx.success("Done", {"extra": "info"})
        console.file.seek(0)
        result = output.getvalue()
        assert "Done" in result
        assert "extra" not in result


class TestOutputContextErrorJsonMode:
    """Tests for OutputContext.error JSON mode behavior."""

    def test_error_outputs_json_without_data(self, capsys) -> None:
        """error should output JSON with schema version wrapper even without data."""
        console = Console()
        ctx = OutputContext(console=console, json_mode=True)

        ctx.error("Something failed")
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["schema_version"] == SCHEMA_VERSION
        assert output["data"]["error"] == "Something failed"


class TestOutputContextErrorNextAction:
    """Tests for OutputContext.error next_action parameter."""

    def test_error_with_next_action_in_json_mode(self, capsys) -> None:
        """error with next_action should include it in JSON output."""
        console = Console()
        ctx = OutputContext(console=console, json_mode=True)

        ctx.error("Run failed", next_action="weld doctor")
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["schema_version"] == SCHEMA_VERSION
        assert output["data"]["error"] == "Run failed"
        assert output["data"]["next_action"] == "weld doctor"

    def test_error_with_next_action_and_data_in_json_mode(self, capsys) -> None:
        """error with next_action and data should include both."""
        console = Console()
        ctx = OutputContext(console=console, json_mode=True)

        ctx.error("Run failed", data={"code": 1}, next_action="weld status")
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["data"]["error"] == "Run failed"
        assert output["data"]["code"] == 1
        assert output["data"]["next_action"] == "weld status"

    def test_error_with_next_action_in_normal_mode(self) -> None:
        """error with next_action should show recovery hint in normal mode."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        ctx = OutputContext(console=console, json_mode=False)

        ctx.error("Something failed", next_action="weld init")
        console.file.seek(0)
        result = output.getvalue()
        assert "Something failed" in result
        assert "weld init" in result

    def test_error_without_next_action_no_hint(self) -> None:
        """error without next_action should not show recovery hint."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        ctx = OutputContext(console=console, json_mode=False)

        ctx.error("Something failed")
        console.file.seek(0)
        result = output.getvalue()
        assert "Something failed" in result
        assert "Run:" not in result


class TestOutputContextDefault:
    """Tests for OutputContext defaults."""

    def test_default_json_mode_is_false(self) -> None:
        """json_mode should default to False."""
        console = Console()
        ctx = OutputContext(console=console)
        assert ctx.json_mode is False
