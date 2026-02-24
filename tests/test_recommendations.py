"""Phase 2.4: Recommendation logic (waiver/add) and endpoint tests."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from analytics_foundry.api import app
from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.gold.recommendations import get_waiver_recommendations


@pytest.fixture(autouse=True)
def clear_bronze():
    bronze_store.clear()
    yield
    bronze_store.clear()


def test_get_waiver_recommendations_returns_list():
    """get_waiver_recommendations returns list of recommendation objects."""
    result = get_waiver_recommendations(league_id=None)
    assert isinstance(result, list)


def test_get_waiver_recommendations_includes_score():
    """Each recommendation has player_id, name, position, team, score."""
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p1", "display_name": "A", "position": "WR", "team": "KC", "trending": 1.5},
        {"player_id": "p2", "display_name": "B", "position": "QB", "team": "BUF"},
    ])
    result = get_waiver_recommendations(league_id=None, limit=10)
    assert len(result) >= 2
    r1 = next(x for x in result if x.get("player_id") == "p1")
    assert "player_id" in r1
    assert "name" in r1
    assert "position" in r1
    assert "team" in r1
    assert "score" in r1
    assert r1["score"] == 1.5
    r2 = next(x for x in result if x.get("player_id") == "p2")
    assert r2["score"] == 0.0


def test_get_waiver_recommendations_respects_limit():
    """get_waiver_recommendations(limit=N) returns at most N items."""
    for i in range(30):
        bronze_store.append_raw("nfl_sleeper", "players", [
            {"player_id": f"p{i}", "display_name": f"P{i}", "position": "WR", "team": "KC"},
        ])
    result = get_waiver_recommendations(league_id=None, limit=5)
    assert len(result) == 5


def test_recommendations_waiver_endpoint_returns_shape():
    """GET /recommendations/waiver returns {recommendations, league_id}."""
    with patch("analytics_foundry.gold.league.ensure_league_ingested", lambda _: None):
        client = TestClient(app)
        resp = client.get("/recommendations/waiver")
    assert resp.status_code == 200
    data = resp.json()
    assert "recommendations" in data
    assert "league_id" in data
    assert isinstance(data["recommendations"], list)


def test_recommendations_waiver_with_league_id():
    """GET /recommendations/waiver?league_id=... returns league_id in response."""
    with patch("analytics_foundry.gold.league.ensure_league_ingested", lambda _: None):
        client = TestClient(app)
        resp = client.get("/recommendations/waiver", params={"league_id": "league_123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["league_id"] == "league_123"
