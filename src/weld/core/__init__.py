"""Core business logic for weld.

This package contains pure business logic with no external I/O:
- plan_parser: Plan parsing and prompt generation
- step_processor: Step management and prompt generation
- review_engine: Review execution and status computation
- loop: Implement-review-fix loop runner
- commit_handler: Commit message building and execution
- run_manager: Run directory and metadata utilities
- artifact_versioning: Version history for research and plan artifacts
- discover_engine: Codebase discovery prompt generation
- interview_engine: Interactive specification refinement
"""

from .artifact_versioning import (
    create_version_snapshot,
    get_current_version,
    get_version_history,
    restore_version,
    update_run_meta_version,
)
from .commit_handler import CommitError, build_commit_message, do_commit, ensure_transcript_gist
from .discover_engine import generate_discover_prompt, get_discover_dir
from .interview_engine import generate_interview_prompt, run_interview_loop
from .lock_manager import LockError, acquire_lock, release_lock, update_heartbeat
from .loop import LoopResult, run_step_loop
from .plan_parser import (
    generate_codex_review_prompt,
    generate_plan_prompt,
    parse_steps,
    parse_steps_lenient,
    parse_steps_strict,
)
from .research_processor import (
    generate_research_prompt,
    get_research_content,
    import_research,
    write_research_prompt,
)
from .review_engine import ReviewError, run_step_review
from .run_manager import (
    create_meta,
    create_run_directory,
    create_spec_ref,
    generate_run_id,
    get_run_dir,
    get_weld_dir,
    hash_config,
    hash_file,
    list_runs,
    sanitize_slug,
)
from .step_processor import (
    create_iter_directory,
    create_step_directory,
    generate_fix_prompt,
    generate_impl_prompt,
    generate_review_prompt,
    get_iter_dir,
    get_step_dir,
)

__all__ = [
    "CommitError",
    "LockError",
    "LoopResult",
    "ReviewError",
    "acquire_lock",
    "build_commit_message",
    "create_iter_directory",
    "create_meta",
    "create_run_directory",
    "create_spec_ref",
    "create_step_directory",
    "create_version_snapshot",
    "do_commit",
    "ensure_transcript_gist",
    "generate_codex_review_prompt",
    "generate_discover_prompt",
    "generate_fix_prompt",
    "generate_impl_prompt",
    "generate_interview_prompt",
    "generate_plan_prompt",
    "generate_research_prompt",
    "generate_review_prompt",
    "generate_run_id",
    "get_current_version",
    "get_discover_dir",
    "get_iter_dir",
    "get_research_content",
    "get_run_dir",
    "get_step_dir",
    "get_version_history",
    "get_weld_dir",
    "hash_config",
    "hash_file",
    "import_research",
    "list_runs",
    "parse_steps",
    "parse_steps_lenient",
    "parse_steps_strict",
    "release_lock",
    "restore_version",
    "run_interview_loop",
    "run_step_loop",
    "run_step_review",
    "sanitize_slug",
    "update_heartbeat",
    "update_run_meta_version",
    "write_research_prompt",
]
