"""Bronze replace_raw_table and replace_rows_matching behavior."""

import json

import pytest

from analytics_foundry.bronze import store as bronze_store


@pytest.fixture(autouse=True)
def clear_bronze():
    bronze_store.clear()
    yield
    bronze_store.clear()


def test_replace_raw_table_overwrites_memory():
    bronze_store.append_raw("nfl_sleeper", "players", [{"player_id": "1"}, {"player_id": "2"}])
    bronze_store.replace_raw_table("nfl_sleeper", "players", [{"player_id": "3"}])
    rows = bronze_store.get_raw("nfl_sleeper", "players")
    assert len(rows) == 1
    assert rows[0]["player_id"] == "3"


def test_replace_rows_matching_scoped_by_league():
    bronze_store.append_raw("nfl_sleeper", "rosters", [
        {"league_id": "A", "roster_id": 1},
        {"league_id": "B", "roster_id": 2},
    ])
    bronze_store.replace_rows_matching(
        "nfl_sleeper",
        "rosters",
        {"league_id": "A"},
        [{"league_id": "A", "roster_id": 99}],
    )
    rows = bronze_store.get_raw("nfl_sleeper", "rosters")
    assert len(rows) == 2
    by_league = {r["league_id"]: r["roster_id"] for r in rows}
    assert by_league["A"] == 99
    assert by_league["B"] == 2


def test_replace_raw_table_rewrites_jsonl():
    bronze_store.append_raw("nfl_sleeper", "players", [{"player_id": "x"}])
    root = bronze_store.get_data_root()
    path = root / "bronze" / "nfl_sleeper" / "players.jsonl"
    bronze_store.replace_raw_table("nfl_sleeper", "players", [{"player_id": "y"}])
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["player_id"] == "y"
