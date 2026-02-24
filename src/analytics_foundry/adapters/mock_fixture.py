"""Second adapter: mock/fixture source to prove pluggability. Writes to bronze without changing core pipeline."""

from typing import Any, Dict, List

from analytics_foundry.adapters.protocol import SourceAdapter
from analytics_foundry.bronze import store as bronze_store


class MockFixtureAdapter:
    """Second domain adapter: in-memory fixture data → bronze. Proves pluggability without core changes."""

    SOURCE_ID = "mock_fixture"

    def __init__(self, records: List[Dict[str, Any]] | None = None, table: str = "events"):
        self._records = records or []
        self._table = table

    @property
    def source_id(self) -> str:
        return self.SOURCE_ID

    def ingest_to_bronze(self, **kwargs: Any) -> None:
        """Write fixture records to bronze. Same pipeline as NFL adapter."""
        bronze_store.append_raw(self.SOURCE_ID, self._table, self._records)
