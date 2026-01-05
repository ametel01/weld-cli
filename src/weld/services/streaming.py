"""Shared streaming subprocess utilities for AI service integrations."""

import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path


class StreamingError(Exception):
    """Streaming subprocess operation failed."""

    pass


def run_streaming_subprocess(
    cmd: list[str],
    text_extractor: Callable[[str], str | None],
    cwd: Path | None = None,
    timeout: int = 600,
    error_class: type[Exception] = StreamingError,
    service_name: str = "Process",
) -> str:
    """Run a subprocess with streaming output and timeout handling.

    This is a shared helper for running AI CLI tools that emit JSONL output.
    It handles timeout checking, process cleanup, and text extraction.

    Args:
        cmd: Command to execute as a list of strings
        text_extractor: Function that extracts text from a JSONL line.
                       Returns str if line contains text, None otherwise.
        cwd: Working directory for the subprocess
        timeout: Timeout in seconds (default: 600)
        error_class: Exception class to raise on errors
        service_name: Name of the service for error messages

    Returns:
        Collected output text as a single string

    Raises:
        error_class: If the process fails, times out, or encounters an error
    """
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # Line buffered
    )

    output_texts: list[str] = []
    assert process.stdout is not None

    try:
        last_text_ended_with_newline = True
        start_time = time.monotonic()

        while True:
            # Check timeout
            if time.monotonic() - start_time > timeout:
                process.terminate()
                process.wait(timeout=5)
                raise error_class(f"{service_name} timed out after {timeout} seconds")

            line = process.stdout.readline()
            if not line:
                # Empty string means EOF
                break

            line = line.strip()
            if not line:
                continue

            text = text_extractor(line)
            if text:
                # Add newline separator between text chunks for readability
                # (each chunk is typically a complete thought/paragraph)
                if output_texts and not last_text_ended_with_newline:
                    sys.stdout.write("\n")
                    output_texts.append("\n")

                sys.stdout.write(text)
                sys.stdout.flush()
                output_texts.append(text)
                last_text_ended_with_newline = text.endswith("\n")

        # Ensure final newline for clean output
        if output_texts and not last_text_ended_with_newline:
            sys.stdout.write("\n")
            output_texts.append("\n")

        process.wait()
        if process.returncode != 0:
            stderr = process.stderr.read() if process.stderr else ""
            raise error_class(f"{service_name} failed: {stderr}")

        return "".join(output_texts)
    finally:
        # Ensure process is terminated on any exception (including KeyboardInterrupt)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
