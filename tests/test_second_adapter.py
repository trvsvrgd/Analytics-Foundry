"""Phase 2.2: Second adapter runs through bronze without changing core pipeline."""

import pytest

from analytics_foundry.adapters.mock_fixture import MockFixtureAdapter
from analytics_foundry.adapters.protocol import SourceAdapter
from analytics_foundry.bronze import store as bronze_store


@pytest.fixture(autouse=True)
def clear_bronze():
    bronze_store.clear()
    yield
    bronze_store.clear()


def test_second_adapter_implements_protocol():
    """Second adapter implements SourceAdapter protocol."""
    adapter = MockFixtureAdapter(records=[{"id": 1}])
    assert isinstance(adapter, SourceAdapter)
    assert adapter.source_id == "mock_fixture"


def test_second_adapter_runs_through_bronze():
    """Second adapter ingest_to_bronze writes to bronze; core pipeline unchanged."""
    records = [{"event_id": "e1", "name": "Event One"}, {"event_id": "e2", "name": "Event Two"}]
    adapter = MockFixtureAdapter(records=records, table="events")
    adapter.ingest_to_bronze()
    raw = bronze_store.get_raw("mock_fixture", "events")
    assert len(raw) == 2
    assert raw[0]["event_id"] == "e1"
    assert raw[1]["name"] == "Event Two"


def test_second_adapter_does_not_require_core_pipeline_changes():
    """Bronze store and protocol work for second adapter without code changes."""
    adapter = MockFixtureAdapter(records=[{"x": 1}])
    adapter.ingest_to_bronze()
    assert bronze_store.get_raw("mock_fixture", "events") == [{"x": 1}]
    # NFL adapter still uses same bronze store
    from analytics_foundry.adapters.nfl_sleeper import NFLSleeperAdapter
    nfl = NFLSleeperAdapter(fetch_players=lambda: {"p1": {"display_name": "P1"}})
    nfl.ingest_to_bronze()
    assert len(bronze_store.get_raw("nfl_sleeper", "players")) == 1
    assert bronze_store.get_raw("mock_fixture", "events") == [{"x": 1}]
