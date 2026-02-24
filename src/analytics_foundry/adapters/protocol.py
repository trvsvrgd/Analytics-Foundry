"""Protocol for source → bronze ingest. Adapters implement this; pipeline stays domain-agnostic."""

from typing import Protocol, runtime_checkable, Any


@runtime_checkable
class SourceAdapter(Protocol):
    """Adapter that fetches raw data from a source and can write/return bronze records."""

    @property
    def source_id(self) -> str:
        """Unique identifier for this source (e.g. 'nfl_sleeper')."""
        ...

    def ingest_to_bronze(self, **kwargs: Any) -> None:
        """Pull from source and write raw records into the bronze layer. Kwargs are source-specific."""
        ...
