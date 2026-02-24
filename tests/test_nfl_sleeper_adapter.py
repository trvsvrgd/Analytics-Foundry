"""PLAN 1.4: Broad ingest and league-scoped ingest land in bronze (fixture/mock)."""

import pytest

from analytics_foundry.adapters.nfl_sleeper import NFLSleeperAdapter
from analytics_foundry.bronze import store as bronze_store


@pytest.fixture(autouse=True)
def clear_bronze():
    """Clear bronze store before each test."""
    bronze_store.clear()
    yield
    bronze_store.clear()


def test_broad_ingest_lands_in_bronze():
    """Broad ingest (no league_id) writes players to bronze."""
    fixture_players = {
        "p1": {"display_name": "Player One", "position": "WR", "team": "KC"},
        "p2": {"display_name": "Player Two", "position": "QB", "team": "BUF"},
    }
    adapter = NFLSleeperAdapter(fetch_players=lambda: fixture_players)
    adapter.ingest_to_bronze()
    records = bronze_store.get_raw("nfl_sleeper", "players")
    assert len(records) == 2
    player_ids = {r["player_id"] for r in records}
    assert player_ids == {"p1", "p2"}
    assert any(r.get("display_name") == "Player One" for r in records)


def test_league_scoped_ingest_lands_in_bronze():
    """League-scoped ingest (league_id=...) writes league, rosters, matchups to bronze."""
    fixture_league = {"name": "My League", "status": "pre_draft"}
    fixture_rosters = [{"roster_id": 1, "owner_id": "u1"}, {"roster_id": 2, "owner_id": "u2"}]
    fixture_matchups = [{"matchup_id": 1}, {"matchup_id": 2}]
    adapter = NFLSleeperAdapter(
        fetch_league=lambda lid: fixture_league if lid == "league_123" else None,
        fetch_rosters=lambda lid: fixture_rosters if lid == "league_123" else [],
        fetch_matchups=lambda lid, week: fixture_matchups if lid == "league_123" else [],
    )
    adapter.ingest_to_bronze(league_id="league_123")
    league_records = bronze_store.get_raw("nfl_sleeper", "league")
    assert len(league_records) == 1
    assert league_records[0]["league_id"] == "league_123"
    assert league_records[0]["name"] == "My League"
    roster_records = bronze_store.get_raw("nfl_sleeper", "rosters")
    assert len(roster_records) == 2
    assert all(r["league_id"] == "league_123" for r in roster_records)
    matchup_records = bronze_store.get_raw("nfl_sleeper", "matchups")
    assert len(matchup_records) == 2
    assert all(m["league_id"] == "league_123" and m["week"] == 1 for m in matchup_records)


def test_nfl_sleeper_implements_source_adapter():
    """NFLSleeperAdapter implements SourceAdapter protocol."""
    from analytics_foundry.adapters.protocol import SourceAdapter

    adapter = NFLSleeperAdapter()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.source_id == "nfl_sleeper"


def test_league_scoped_ingest_handles_missing_league():
    """League-scoped ingest still writes rosters/matchups when league fetch returns None."""
    adapter = NFLSleeperAdapter(
        fetch_league=lambda lid: None,
        fetch_rosters=lambda lid: [{"roster_id": 1}] if lid == "missing_league" else [],
        fetch_matchups=lambda lid, week: [{"matchup_id": 1}] if lid == "missing_league" else [],
    )
    adapter.ingest_to_bronze(league_id="missing_league")
    league_records = bronze_store.get_raw("nfl_sleeper", "league")
    assert len(league_records) == 0
    roster_records = bronze_store.get_raw("nfl_sleeper", "rosters")
    assert len(roster_records) == 1
    assert roster_records[0]["league_id"] == "missing_league"


def test_ensure_league_ingested_lazy_fetch():
    """API-layer hook: ensure_league_ingested(league_id) triggers league-scoped ingest when adapter is available."""
    from unittest.mock import patch

    from analytics_foundry.gold.league import ensure_league_ingested

    adapter = NFLSleeperAdapter(
        fetch_league=lambda lid: {"name": "Lazy League"} if lid == "lazy_123" else None,
        fetch_rosters=lambda lid: [{"roster_id": 1}] if lid == "lazy_123" else [],
        fetch_matchups=lambda lid, week: [] if lid == "lazy_123" else [],
    )
    with patch("analytics_foundry.gold.league.get_adapter", return_value=adapter):
        ensure_league_ingested("lazy_123")
    league_records = bronze_store.get_raw("nfl_sleeper", "league")
    assert len(league_records) == 1
    assert league_records[0]["league_id"] == "lazy_123"
    assert league_records[0]["name"] == "Lazy League"
