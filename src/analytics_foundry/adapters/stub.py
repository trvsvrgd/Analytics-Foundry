"""Stub adapter for testing and as a template for real adapters."""

from typing import Any

from analytics_foundry.adapters.protocol import SourceAdapter


class StubSourceAdapter:
    """Concrete stub: implements SourceAdapter, does no I/O. Used to verify interface and registry."""

    @property
    def source_id(self) -> str:
        return "stub"

    def ingest_to_bronze(self, **kwargs: Any) -> None:
        pass
