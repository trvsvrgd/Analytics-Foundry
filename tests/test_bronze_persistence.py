"""Tests for bronze store local file persistence."""

import json

import pytest

from analytics_foundry.bronze import store as bronze_store


@pytest.fixture(autouse=True)
def clear_bronze():
    bronze_store.clear()
    yield
    bronze_store.clear()


def test_append_raw_persists_to_jsonl():
    """When FOUNDRY_DATA_DIR is set, append_raw writes to data/bronze/{source_id}/{table}.jsonl."""
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p1", "name": "A"},
        {"player_id": "p2", "name": "B"},
    ])
    root = bronze_store.get_data_root()
    assert root is not None
    path = root / "bronze" / "nfl_sleeper" / "players.jsonl"
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"player_id": "p1", "name": "A"}
    assert json.loads(lines[1]) == {"player_id": "p2", "name": "B"}


def test_get_raw_returns_persisted_data():
    """append_raw then get_raw returns the same records (persisted then read)."""
    bronze_store.append_raw("other", "t", [{"x": 1}])
    data = bronze_store.get_raw("other", "t")
    assert data == [{"x": 1}]


def test_list_tables_includes_persisted_tables():
    """list_tables() includes bronze tables found on disk (e.g. after load_from_disk)."""
    bronze_store.append_raw("src1", "t1", [{"a": 1}])
    bronze_store.append_raw("src1", "t2", [{"b": 2}, {"b": 3}])
    tables = bronze_store.list_tables()
    assert ("src1", "t1", 1) in tables
    assert ("src1", "t2", 2) in tables


def test_clear_removes_persisted_files():
    """clear() removes bronze jsonl files for tables that were in memory."""
    bronze_store.append_raw("nfl_sleeper", "players", [{"id": "1"}])
    root = bronze_store.get_data_root()
    path = root / "bronze" / "nfl_sleeper" / "players.jsonl"
    assert path.is_file()
    bronze_store.clear()
    assert not path.is_file()
