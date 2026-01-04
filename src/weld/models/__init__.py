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

from .issues import Issue, Issues
from .meta import Meta, SpecRef
from .status import Status
from .step import Step

__all__ = ["Issue", "Issues", "Meta", "SpecRef", "Status", "Step"]
