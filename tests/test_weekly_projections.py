"""Phase 1.8: Tests for Weekly NFL Feed source adapter, conformed silver layers, and gold projection models."""

import pytest
from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.adapters.nfl_weekly_feed import NFLWeeklyFeedAdapter
from analytics_foundry.silver import projections as silver_projections
from analytics_foundry.gold import projections as gold_projections


@pytest.fixture(autouse=True)
def clear_bronze_each():
    bronze_store.clear()
    yield
    bronze_store.clear()


def test_weekly_feed_adapter_ingestion():
    """NFLWeeklyFeedAdapter writes matchups and stats to bronze."""
    adapter = NFLWeeklyFeedAdapter()
    adapter.ingest_to_bronze()

    matchups = bronze_store.get_raw("nfl_weekly_feed", "weekly_matchups")
    assert len(matchups) == 4
    assert matchups[0]["home_team"] == "KC"

    stats = bronze_store.get_raw("nfl_weekly_feed", "team_stats")
    assert len(stats) == 8
    assert any(s["team"] == "NYJ" and s["offensive_rank"] == 32 for s in stats)


def test_silver_projections_conformed():
    """Silver layer cleans and conforms stats and matchups."""
    bronze_store.append_raw("nfl_weekly_feed", "weekly_matchups", [
        {"matchup_id": "99", "week": "2", "home_team": "kc", "away_team": "buf", "home_qb_backup": 1},
    ])
    bronze_store.append_raw("nfl_weekly_feed", "team_stats", [
        {"team": "kc", "offensive_rank": "5", "defensive_rank": "10"},
    ])

    matchups = silver_projections.get_weekly_matchups()
    assert len(matchups) == 1
    assert matchups[0]["matchup_id"] == 99
    assert matchups[0]["week"] == 2
    assert matchups[0]["home_team"] == "kc"
    assert matchups[0]["home_qb_backup"] is True

    stats = silver_projections.get_team_stats()
    assert len(stats) == 1
    assert stats[0]["team"] == "KC"
    assert stats[0]["offensive_rank"] == 5
    assert stats[0]["defensive_rank"] == 10


def test_gold_defense_projections():
    """Gold defense projections calculates expected points based on ranks, history, and backup QBs."""
    # Setup stats: SF has defense rank 1. NYJ has offense rank 32.
    # Matchup: SF vs NYJ (no backup QB).
    # Expected: 10.0 + (32 - 16) * 0.5 + (16 - 1) * 0.3 = 10.0 + 8.0 + 4.5 = 22.5
    matchups = [
        {"matchup_id": 10, "week": 1, "home_team": "SF", "away_team": "NYJ", "home_qb_backup": False, "away_qb_backup": False}
    ]
    stats = [
        {"team": "SF", "offensive_rank": 1, "defensive_rank": 1, "historical_win_rate": 0.8},
        {"team": "NYJ", "offensive_rank": 32, "defensive_rank": 10, "historical_win_rate": 0.3},
    ]
    bronze_store.append_raw("nfl_weekly_feed", "weekly_matchups", matchups)
    bronze_store.append_raw("nfl_weekly_feed", "team_stats", stats)

    projs = gold_projections.get_defense_projections()
    sf_proj = next(x for x in projs if x["team"] == "SF")
    assert sf_proj["opponent"] == "NYJ"
    assert sf_proj["projected_points"] == 22.5

    # Test backup QB: add 5.0 points
    matchups_backup = [
        {"matchup_id": 10, "week": 1, "home_team": "SF", "away_team": "NYJ", "home_qb_backup": False, "away_qb_backup": True}
    ]
    bronze_store.clear()
    bronze_store.append_raw("nfl_weekly_feed", "weekly_matchups", matchups_backup)
    bronze_store.append_raw("nfl_weekly_feed", "team_stats", stats)

    projs_backup = gold_projections.get_defense_projections()
    sf_proj_b = next(x for x in projs_backup if x["team"] == "SF")
    assert sf_proj_b["backup_qb_playing"] is True
    assert sf_proj_b["projected_points"] == 27.5


def test_gold_win_probability_calculations():
    """Gold win probability correctly resolves matchups, roster defenses, and clamps probabilities."""
    # Ingest rosters, players, and matchups for a league
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p_sf_def", "full_name": "SF Defense", "position": "DEF", "team": "SF", "trending": 0.5},
        {"player_id": "p_nyj_def", "full_name": "NYJ Defense", "position": "DEF", "team": "NYJ", "trending": -0.2},
    ])
    bronze_store.append_raw("nfl_sleeper", "rosters", [
        {"league_id": "L1", "roster_id": 1, "players": ["p_sf_def"]},
        {"league_id": "L1", "roster_id": 2, "players": ["p_nyj_def"]},
    ])
    bronze_store.append_raw("nfl_sleeper", "matchups", [
        {"league_id": "L1", "matchup_id": 5, "roster_id": 1, "players": ["p_sf_def"]},
        {"league_id": "L1", "matchup_id": 5, "roster_id": 2, "players": ["p_nyj_def"]},
    ])

    # Weekly feed
    matchups = [
        {"matchup_id": 1, "week": 1, "home_team": "SF", "away_team": "NYJ", "home_qb_backup": False, "away_qb_backup": False}
    ]
    stats = [
        {"team": "SF", "offensive_rank": 1, "defensive_rank": 1, "historical_win_rate": 0.8},
        {"team": "NYJ", "offensive_rank": 32, "defensive_rank": 10, "historical_win_rate": 0.3},
    ]
    bronze_store.append_raw("nfl_weekly_feed", "weekly_matchups", matchups)
    bronze_store.append_raw("nfl_weekly_feed", "team_stats", stats)

    # Calculate
    win_probs = gold_projections.get_win_probability("L1")
    assert len(win_probs) == 1
    w = win_probs[0]
    assert w["roster_id_a"] == 1
    assert w["roster_id_b"] == 2
    # Roster 1 has SF Defense (proj 22.5, trending 0.5)
    # Roster 2 has NYJ Defense (proj 10.0 + (1-16)*0.5 + (16-10)*0.3 = 10.0 - 7.5 + 1.8 = 4.3, trending -0.2)
    # diff = (0.5 - (-0.2))*0.1 + (22.5 - 4.3)*0.02 = 0.07 + 0.364 = 0.434
    # prob_a = 0.50 + 0.434 = 0.934 -> Clamped to 0.90
    assert w["win_probability_a"] == 0.90
    assert w["win_probability_b"] == 0.10
