"""Core business logic for weld.

This package contains pure business logic with no external I/O:
- history: Command history tracking
- weld_dir: Weld directory utilities
- discover_engine: Codebase discovery prompt generation
- interview_engine: Interactive specification refinement
- doc_review_engine: Document review against codebase
"""

from .discover_engine import generate_discover_prompt, get_discover_dir
from .doc_review_engine import (
    generate_code_review_prompt,
    generate_doc_review_prompt,
    get_doc_review_dir,
    strip_preamble,
)
from .history import HistoryEntry, get_history_path, log_command, prune_history, read_history
from .interview_engine import generate_interview_prompt, run_interview_loop
from .plan_parser import (
    Phase,
    Plan,
    Step,
    ValidationResult,
    is_complete,
    mark_complete,
    mark_phase_complete,
    mark_step_complete,
    parse_plan,
    validate_plan,
)
from .weld_dir import get_weld_dir

__all__ = [
    "HistoryEntry",
    "Phase",
    "Plan",
    "Step",
    "ValidationResult",
    "generate_code_review_prompt",
    "generate_discover_prompt",
    "generate_doc_review_prompt",
    "generate_interview_prompt",
    "get_discover_dir",
    "get_doc_review_dir",
    "get_history_path",
    "get_weld_dir",
    "is_complete",
    "log_command",
    "mark_complete",
    "mark_phase_complete",
    "mark_step_complete",
    "parse_plan",
    "prune_history",
    "read_history",
    "run_interview_loop",
    "strip_preamble",
    "validate_plan",
]
