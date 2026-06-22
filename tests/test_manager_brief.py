"""Manager brief data product contract tests."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from analytics_foundry.api import app
from analytics_foundry.gold.manager_brief import get_manager_brief


def test_manager_brief_packages_model_outputs_and_priority_actions():
    with patch(
        "analytics_foundry.gold.manager_brief.gold_recommendations.get_waiver_recommendations",
        return_value=[{"player_id": "p_wr1", "name": "Breakout WR", "score": 99.0}],
    ), patch(
        "analytics_foundry.gold.manager_brief.gold_tuesday.get_waiver_targets",
        return_value=[
            {
                "player_id": "p_wr1",
                "player_name": "Breakout WR",
                "position": "WR",
                "team": "KC",
                "recommendation_score": 99.5,
                "breakout_reason": "Snap increase of 45%",
            }
        ],
    ), patch(
        "analytics_foundry.gold.manager_brief.gold_tuesday.get_waiver_bids",
        return_value=[
            {
                "player_id": "p_wr1",
                "player_name": "Breakout WR",
                "predicted_winning_bid": 6,
                "predicted_runner_up_bid": 3,
            }
        ],
    ), patch(
        "analytics_foundry.gold.manager_brief.gold_tuesday.get_trade_regression",
        return_value=[
            {
                "player_id": "p_buy",
                "player_name": "Buy WR",
                "position": "WR",
                "team": "BUF",
                "points_difference": 8.5,
                "recommendation": "Buy-Low",
            }
        ],
    ), patch(
        "analytics_foundry.gold.manager_brief.gold_tuesday.get_injury_cascade",
        return_value=[
            {
                "injured_player_id": "p_rb1",
                "injured_player_name": "Starter RB",
                "backup_player_id": "p_rb2",
                "backup_player_name": "Backup RB",
                "position": "RB",
                "team": "DAL",
                "projected_points_gain": 9.0,
            }
        ],
    ), patch(
        "analytics_foundry.gold.manager_brief.gold_tuesday.get_roster_utility",
        return_value=[
            {
                "player_id": "p_drop",
                "player_name": "Drop WR",
                "position": "WR",
                "team": "CHI",
                "expected_points": 0.5,
                "utility_classification": "Drop Candidate",
            }
        ],
    ), patch(
        "analytics_foundry.gold.manager_brief.gold_projections.get_defense_projections",
        return_value=[{"team": "SF", "opponent": "NYJ", "projected_points": 22.5}],
    ), patch(
        "analytics_foundry.gold.manager_brief.gold_projections.get_win_probability",
        return_value=[{"matchup_id": 5, "win_probability_a": 0.39, "win_probability_b": 0.61}],
    ):
        brief = get_manager_brief("L1", limit=10)

    assert brief["league_id"] == "L1"
    assert brief["summary"]["waiver_targets"] == 1
    assert brief["summary"]["trade_signals"] == 1
    assert brief["summary"]["drop_candidates"] == 1
    assert brief["models"]["waiver_recommendations"][0]["player_id"] == "p_wr1"
    assert brief["priority_actions"][0]["category"] == "Waiver"
    assert brief["priority_actions"][0]["estimated_bid"] == 6
    assert {action["category"] for action in brief["priority_actions"]} >= {
        "Waiver",
        "Injury",
        "Trade",
        "Roster",
        "Lineup",
        "Matchup",
    }


def test_manager_brief_endpoint_uses_default_shape():
    payload = {
        "league_id": "league_123",
        "generated_at": "2026-06-16T00:00:00Z",
        "summary": {"priority_actions": 0},
        "priority_actions": [],
        "models": {},
    }
    with patch("analytics_foundry.gold.league.ensure_league_ingested", lambda _: None), patch(
        "analytics_foundry.api.gold_manager_brief.get_manager_brief",
        return_value=payload,
    ) as mock_brief:
        client = TestClient(app)
        resp = client.get("/recommendations/manager-brief", params={"league_id": "league_123", "limit": 5})

    assert resp.status_code == 200
    assert resp.json() == payload
    mock_brief.assert_called_once_with(league_id="league_123", limit=5)
