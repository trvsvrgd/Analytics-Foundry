"""Registry for source adapters. Register by source_id; look up for pipeline execution."""

from typing import Dict, Optional, Type

from analytics_foundry.adapters.protocol import SourceAdapter

_REGISTRY: Dict[str, type] = {}


def register_adapter(adapter_class: Type[SourceAdapter]) -> None:
    """Register an adapter class by its source_id (from an instance or the class default)."""
    # Instantiate temporarily to read source_id, or use class attribute if we add one
    inst = adapter_class()
    _REGISTRY[inst.source_id] = adapter_class


def get_adapter(source_id: str) -> Optional[SourceAdapter]:
    """Return an adapter instance for the given source_id, or None."""
    cls = _REGISTRY.get(source_id)
    return cls() if cls is not None else None


def clear_registry() -> None:
    """Clear all registrations (for tests)."""
    _REGISTRY.clear()
