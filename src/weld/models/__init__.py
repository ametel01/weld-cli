"""Pydantic data models for weld run artifacts.

This package defines the data structures used throughout weld for:
- Run metadata and spec references (Meta, SpecRef)
- Parsed plan steps (Step)
- Review issues and results (Issue, Issues)
- Iteration status tracking (Status)

All models are Pydantic BaseModel subclasses, enabling:
- Automatic JSON serialization/deserialization
- Field validation and type coercion
- Schema generation for documentation

Example:
    >>> from weld.models import Step, Status
    >>> step = Step(n=1, title="Setup", slug="setup", body_md="...")
    >>> step.model_dump_json()
"""

from .discover import DiscoverMeta
from .issues import Issue, Issues
from .lock import Lock
from .meta import Meta, SpecRef
from .status import CategoryResult, ChecksSummary, Status
from .step import Step
from .timing import Timing
from .version_info import MAX_VERSIONS, CommandEvent, StaleOverride, VersionInfo

__all__ = [
    "MAX_VERSIONS",
    "CategoryResult",
    "ChecksSummary",
    "CommandEvent",
    "DiscoverMeta",
    "Issue",
    "Issues",
    "Lock",
    "Meta",
    "SpecRef",
    "StaleOverride",
    "Status",
    "Step",
    "Timing",
    "VersionInfo",
]
