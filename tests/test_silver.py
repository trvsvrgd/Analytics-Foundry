"""Phase 1.5: Silver layer — schema conformance and dedup logic."""

import pytest

from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.silver import injuries as silver_injuries
from analytics_foundry.silver import league as silver_league
from analytics_foundry.silver import players as silver_players
from analytics_foundry.silver import rosters as silver_rosters
from analytics_foundry.silver.players import SILVER_PLAYER_KEYS
from analytics_foundry.silver.league import SILVER_LEAGUE_KEYS
from analytics_foundry.silver.rosters import SILVER_ROSTER_KEYS
from analytics_foundry.silver.injuries import SILVER_INJURY_KEYS


@pytest.fixture(autouse=True)
def clear_bronze():
    bronze_store.clear()
    yield
    bronze_store.clear()


def test_silver_players_schema_conforms():
    """Silver players output conforms to expected schema: player_id, name, position, team, status, injury_status, age, trending, updated_at."""
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p1", "display_name": "Alice", "position": "WR", "team": "KC", "status": "Active"},
    ])
    result = silver_players.get_players()
    assert len(result) == 1
    p = result[0]
    for key in SILVER_PLAYER_KEYS:
        assert key in p
    assert p["player_id"] == "p1"
    assert p["name"] == "Alice"
    assert p["position"] == "WR"
    assert p["team"] == "KC"
    assert p["status"] == "Active"
    assert p["injury_status"] == ""
    assert p["age"] is None
    assert p["trending"] is None


def test_silver_players_dedup_latest_wins():
    """Silver players deduplicates by player_id; latest record wins."""
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p1", "display_name": "Old Name", "position": "WR"},
        {"player_id": "p1", "display_name": "New Name", "position": "QB"},
    ])
    result = silver_players.get_players()
    assert len(result) == 1
    assert result[0]["name"] == "New Name"
    assert result[0]["position"] == "QB"


def test_silver_players_coerces_types():
    """Silver players coerces age to int, trending to float."""
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p1", "age": "25", "trending": "1.5"},
    ])
    result = silver_players.get_players()
    assert result[0]["age"] == 25
    assert result[0]["trending"] == 1.5


def test_silver_league_schema_conforms():
    """Silver league output conforms to expected schema: league_id, name."""
    bronze_store.append_raw("nfl_sleeper", "league", [
        {"league_id": "L1", "name": "My League"},
    ])
    result = silver_league.get_leagues()
    assert len(result) == 1
    lg = result[0]
    for key in SILVER_LEAGUE_KEYS:
        assert key in lg
    assert lg["league_id"] == "L1"
    assert lg["name"] == "My League"


def test_silver_league_dedup_latest_wins():
    """Silver league deduplicates by league_id; latest wins."""
    bronze_store.append_raw("nfl_sleeper", "league", [
        {"league_id": "L1", "name": "Old Name"},
        {"league_id": "L1", "name": "New Name"},
    ])
    result = silver_league.get_leagues()
    assert len(result) == 1
    assert result[0]["name"] == "New Name"


def test_silver_rosters_schema_conforms():
    """Silver rosters output conforms to expected schema: league_id, roster_id, players."""
    bronze_store.append_raw("nfl_sleeper", "rosters", [
        {"league_id": "L1", "roster_id": 1, "players": ["p1", "p2"]},
    ])
    result = silver_rosters.get_rosters()
    assert len(result) == 1
    r = result[0]
    for key in SILVER_ROSTER_KEYS:
        assert key in r
    assert r["league_id"] == "L1"
    assert r["roster_id"] == 1
    assert r["players"] == ["p1", "p2"]


def test_silver_rosters_dedup_latest_wins():
    """Silver rosters deduplicates by (league_id, roster_id); latest wins."""
    bronze_store.append_raw("nfl_sleeper", "rosters", [
        {"league_id": "L1", "roster_id": 1, "players": ["p1"]},
        {"league_id": "L1", "roster_id": 1, "players": ["p1", "p2", "p3"]},
    ])
    result = silver_rosters.get_rosters()
    assert len(result) == 1
    assert result[0]["players"] == ["p1", "p2", "p3"]


def test_silver_rosters_get_rostered_player_ids():
    """get_rostered_player_ids returns set of player_ids on rosters for league."""
    bronze_store.append_raw("nfl_sleeper", "rosters", [
        {"league_id": "L1", "roster_id": 1, "players": ["p1", "p2"]},
        {"league_id": "L1", "roster_id": 2, "players": ["p3"]},
    ])
    ids = silver_rosters.get_rostered_player_ids("L1")
    assert ids == {"p1", "p2", "p3"}
    ids_other = silver_rosters.get_rostered_player_ids("L2")
    assert ids_other == set()


def test_silver_injuries_schema_conforms():
    """Silver injuries output conforms to expected schema: player_id, status, updated_at."""
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p1", "injury_status": "Out", "updated_at": "2024-01-01"},
    ])
    result = silver_injuries.get_injuries()
    assert len(result) == 1
    i = result[0]
    for key in SILVER_INJURY_KEYS:
        assert key in i
    assert i["player_id"] == "p1"
    assert i["status"] == "Out"
    assert i["updated_at"] == "2024-01-01"


def test_silver_injuries_excludes_active():
    """Silver injuries excludes players with status Active or empty."""
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p1", "injury_status": "Out"},
        {"player_id": "p2", "injury_status": "Active"},
        {"player_id": "p3", "status": ""},
    ])
    result = silver_injuries.get_injuries()
    assert len(result) == 1
    assert result[0]["player_id"] == "p1"
