"""Phase 1.9: Tests for Tuesday Evening Analytics (Waiver Targets, Trade Regression, Injury Cascade, Roster Utility, FAAB Bid Predictor)."""

import pytest
from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.adapters.nfl_weekly_feed import NFLWeeklyFeedAdapter
from analytics_foundry.silver import tuesday_analytics as silver_tuesday
from analytics_foundry.gold import tuesday_analytics as gold_tuesday


@pytest.fixture(autouse=True)
def clear_bronze_each():
    bronze_store.clear()
    yield
    bronze_store.clear()


def test_tuesday_feed_adapter_ingests_all_new_tables():
    """NFLWeeklyFeedAdapter ingests stats, depth charts, vegas weather, and faab history."""
    adapter = NFLWeeklyFeedAdapter()
    adapter.ingest_to_bronze()

    p_stats = bronze_store.get_raw("nfl_weekly_feed", "player_weekly_stats")
    assert len(p_stats) == 4
    assert p_stats[0]["player_id"] == "p_wr1"

    charts = bronze_store.get_raw("nfl_weekly_feed", "depth_charts")
    assert len(charts) == 4
    assert charts[0]["team"] == "KC"

    weather = bronze_store.get_raw("nfl_weekly_feed", "vegas_weather")
    assert len(weather) == 3
    assert weather[0]["home_team"] == "KC"

    faab = bronze_store.get_raw("nfl_weekly_feed", "faab_history")
    assert len(faab) == 3
    assert faab[0]["roster_id"] == 1


def test_silver_tuesday_conforms_data():
    """Silver layer conformed accessors return cleanly cast dictionary lists."""
    bronze_store.append_raw("nfl_weekly_feed", "player_weekly_stats", [
        {"player_id": "p1", "week": "2", "snaps_pct": "0.75", "targets": "5", "expected_points": "12.5"},
    ])
    bronze_store.append_raw("nfl_weekly_feed", "depth_charts", [
        {"team": "kc", "position": "rb", "players": ["p1", "p2"]},
    ])
    bronze_store.append_raw("nfl_weekly_feed", "vegas_weather", [
        {"home_team": "kc", "away_team": "lac", "over_under": "48.5", "is_dome": "false"},
    ])
    bronze_store.append_raw("nfl_weekly_feed", "faab_history", [
        {"roster_id": "1", "remaining_faab": "80", "bid_history": [{"player_id": "p1", "bid": "10", "success": "true"}]},
    ])

    stats = silver_tuesday.get_player_weekly_stats()
    assert len(stats) == 1
    assert stats[0]["player_id"] == "p1"
    assert stats[0]["snaps_pct"] == 0.75
    assert stats[0]["targets"] == 5
    assert stats[0]["expected_points"] == 12.5

    charts = silver_tuesday.get_depth_charts()
    assert len(charts) == 1
    assert charts[0]["team"] == "KC"
    assert charts[0]["position"] == "RB"
    assert charts[0]["players"] == ["p1", "p2"]

    weather = silver_tuesday.get_vegas_weather()
    assert len(weather) == 1
    assert weather[0]["home_team"] == "KC"
    assert weather[0]["over_under"] == 48.5
    assert weather[0]["is_dome"] is False

    faab = silver_tuesday.get_faab_history()
    assert len(faab) == 1
    assert faab[0]["roster_id"] == 1
    assert faab[0]["remaining_faab"] == 80
    assert faab[0]["bid_history"] == [{"player_id": "p1", "bid": 10, "success": True}]


def test_gold_waiver_targets_breakouts():
    """Gold waiver targets correctly identifies snap growth and route breakouts."""
    # Setup unrostered players: p_wr1 is route breakout, p_rb_backup is standard backup
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p_wr1", "full_name": "Breakout WR", "position": "WR", "team": "KC"},
        {"player_id": "p_rb_backup", "full_name": "Backup RB", "position": "RB", "team": "KC"},
    ])
    bronze_store.append_raw("nfl_weekly_feed", "player_weekly_stats", [
        {"player_id": "p_wr1", "week": 2, "snaps_pct": 0.85, "snaps_pct_prev": 0.40, "routes_run_pct": 0.90, "targets": 2},
        {"player_id": "p_rb_backup", "week": 2, "snaps_pct": 0.10, "snaps_pct_prev": 0.08, "routes_run_pct": 0.05, "targets": 1},
    ])

    targets = gold_tuesday.get_waiver_targets()
    assert len(targets) == 1
    t = targets[0]
    assert t["player_id"] == "p_wr1"
    assert t["player_name"] == "Breakout WR"
    assert "Snap increase of 45%" in t["breakout_reason"]
    assert "Route participation of 90%" in t["breakout_reason"]
    assert t["recommendation_score"] > 50.0


def test_gold_trade_regression():
    """Gold trade regression correctly flags buy-low and sell-high trade candidates."""
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p_wr1", "full_name": "Buy WR", "position": "WR", "team": "KC"},
        {"player_id": "p_rb1", "full_name": "Sell RB", "position": "RB", "team": "KC"},
    ])
    # p_wr1: expected 14.5, actual 4.2 -> diff 10.3 -> Buy-low
    # p_rb1: expected 12.0, actual 26.5 -> diff -14.5 -> Sell-high
    bronze_store.append_raw("nfl_weekly_feed", "player_weekly_stats", [
        {"player_id": "p_wr1", "week": 2, "actual_points": 4.2, "expected_points": 14.5, "touchdowns": 0},
        {"player_id": "p_rb1", "week": 2, "actual_points": 26.5, "expected_points": 12.0, "touchdowns": 3},
    ])

    regression = gold_tuesday.get_trade_regression()
    assert len(regression) == 2
    r_wr = next(x for x in regression if x["player_id"] == "p_wr1")
    assert r_wr["recommendation"] == "Buy-Low"
    r_rb = next(x for x in regression if x["player_id"] == "p_rb1")
    assert r_rb["recommendation"] == "Sell-High"


def test_gold_injury_depth_chart_cascade():
    """Gold injury cascade accurately detects injured starters and projects backup gains."""
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p_kc_rb1", "full_name": "Starter RB", "position": "RB", "team": "KC", "injury_status": "Out"},
        {"player_id": "p_kc_rb2", "full_name": "Backup RB", "position": "RB", "team": "KC", "injury_status": "Active"},
    ])
    bronze_store.append_raw("nfl_weekly_feed", "depth_charts", [
        {"team": "KC", "position": "RB", "players": ["p_kc_rb1", "p_kc_rb2", "p_kc_rb3"]},
    ])

    cascade = gold_tuesday.get_injury_cascade()
    assert len(cascade) == 1
    c = cascade[0]
    assert c["injured_player_id"] == "p_kc_rb1"
    assert c["backup_player_id"] == "p_kc_rb2"
    assert c["backup_player_name"] == "Backup RB"
    assert c["projected_points_gain"] == 9.0  # 12.0 * 0.75


def test_gold_bench_utility_audit():
    """Gold roster utility correctly classifies starters, handcuffs, and drop candidates."""
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p_kc_rb1", "full_name": "Starter RB", "position": "RB", "team": "KC"},
        {"player_id": "p_kc_rb2", "full_name": "Handcuff RB", "position": "RB", "team": "KC"},
        {"player_id": "p_drop", "full_name": "Useless WR", "position": "WR", "team": "KC"},
    ])
    bronze_store.append_raw("nfl_sleeper", "rosters", [
        {"league_id": "L1", "roster_id": 1, "players": ["p_kc_rb1", "p_kc_rb2", "p_drop"]},
    ])
    bronze_store.append_raw("nfl_weekly_feed", "depth_charts", [
        {"team": "KC", "position": "RB", "players": ["p_kc_rb1", "p_kc_rb2"]},
    ])
    bronze_store.append_raw("nfl_weekly_feed", "player_weekly_stats", [
        {"player_id": "p_kc_rb1", "week": 2, "snaps_pct": 0.80, "expected_points": 14.5},
        {"player_id": "p_kc_rb2", "week": 2, "snaps_pct": 0.15, "expected_points": 1.5},
        {"player_id": "p_drop", "week": 2, "snaps_pct": 0.05, "expected_points": 0.5},
    ])

    utility = gold_tuesday.get_roster_utility("L1")
    assert len(utility) == 3
    u_starter = next(x for x in utility if x["player_id"] == "p_kc_rb1")
    assert u_starter["utility_classification"] == "Core Starter"
    u_handcuff = next(x for x in utility if x["player_id"] == "p_kc_rb2")
    assert u_handcuff["utility_classification"] == "Must-Hold Handcuff"
    u_drop = next(x for x in utility if x["player_id"] == "p_drop")
    assert u_drop["utility_classification"] == "Drop Candidate"


def test_gold_waiver_bid_predictor():
    """Gold waiver bid optimizer estimates bids based on budgets and rival needs."""
    # Setup waiver target player p_wr1
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p_wr1", "full_name": "Breakout WR", "position": "WR", "team": "KC"},
        {"player_id": "p_other", "full_name": "Opponent player", "position": "RB", "team": "BUF"},
        {"player_id": "p_wr_other", "full_name": "Other WR", "position": "WR", "team": "BUF"},
    ])
    # Roster 1 has only 1 WR (p_wr1 not owned). Needs WR. FAAB: 80.
    # Roster 2 has only 1 WR. Needs WR. FAAB: 40.
    # Roster 3 has 4 WRs. Doesn't need WR. FAAB: 100.
    bronze_store.append_raw("nfl_sleeper", "rosters", [
        {"league_id": "L1", "roster_id": 1, "players": ["p_other"]},
        {"league_id": "L1", "roster_id": 2, "players": ["p_other"]},
        {"league_id": "L1", "roster_id": 3, "players": ["p_wr_other", "p_wr_other", "p_wr_other", "p_wr_other"]},
    ])
    bronze_store.append_raw("nfl_weekly_feed", "player_weekly_stats", [
        {"player_id": "p_wr1", "week": 2, "snaps_pct": 0.85, "snaps_pct_prev": 0.40, "routes_run_pct": 0.90, "targets": 2},
    ])
    bronze_store.append_raw("nfl_weekly_feed", "faab_history", [
        {"roster_id": 1, "remaining_faab": 80},
        {"roster_id": 2, "remaining_faab": 40},
        {"roster_id": 3, "remaining_faab": 100},
    ])

    bids = gold_tuesday.get_waiver_bids("L1")
    assert len(bids) == 1
    b = bids[0]
    assert b["player_id"] == "p_wr1"
    # Target score is 50.0 + (0.85-0.4)*50 + 0.9*30 = 50.0 + 22.5 + 27.0 = 99.5 (score >= 70)
    # Roster 1: 80 FAAB * 0.08 = 6.4 -> 6 estimated bid
    # Roster 2: 40 FAAB * 0.08 = 3.2 -> 3 estimated bid
    assert b["predicted_winning_bid"] == 6
    assert b["predicted_runner_up_bid"] == 3
