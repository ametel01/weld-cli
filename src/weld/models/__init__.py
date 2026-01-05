"""Pydantic data models for weld.

This package defines the data structures used throughout weld for:
- Discover metadata (DiscoverMeta)
- Review issues and results (Issue, Issues)

All models are Pydantic BaseModel subclasses, enabling:
- Automatic JSON serialization/deserialization
- Field validation and type coercion
- Schema generation for documentation
"""

from .discover import DiscoverMeta
from .issues import Issue, Issues

__all__ = [
    "DiscoverMeta",
    "Issue",
    "Issues",
]
