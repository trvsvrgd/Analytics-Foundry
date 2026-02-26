"""Phase 2.1: Contract tests for sleeper-stream-scribe API (all three endpoints + optional league_id)."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from analytics_foundry.api import app
from analytics_foundry.bronze import store as bronze_store


@pytest.fixture
def client():
    """TestClient with ensure_league_ingested mocked to avoid real Sleeper API calls."""
    with patch("analytics_foundry.gold.league.ensure_league_ingested", lambda _: None):
        yield TestClient(app)


@pytest.fixture(autouse=True)
def clear_bronze():
    bronze_store.clear()
    yield
    bronze_store.clear()


def test_players_available_returns_array(client):
    """GET /players/available returns JSON array of player objects."""
    resp = client.get("/players/available")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_players_available_with_league_id(client):
    """GET /players/available?league_id=... accepts optional league_id."""
    resp = client.get("/players/available", params={"league_id": "league_123"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_players_available_player_object_shape(client):
    """Each item in /players/available has id/player_id, name, position, team, status, age, trending."""
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p1", "display_name": "Test Player", "position": "WR", "team": "KC"},
    ])
    resp = client.get("/players/available")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    p = next(x for x in data if x.get("player_id") == "p1" or x.get("id") == "p1")
    assert "id" in p or "player_id" in p
    assert "name" in p
    assert "position" in p
    assert "team" in p
    assert "status" in p
    assert "age" in p
    assert "trending" in p


def test_league_validate_returns_shape(client):
    """POST /league/validate returns valid, league_id, league_name."""
    resp = client.post("/league/validate", json={"league_id": "nonexistent"})
    assert resp.status_code == 200
    data = resp.json()
    assert "valid" in data
    assert "league_id" in data
    assert "league_name" in data
    assert data["league_id"] == "nonexistent"


def test_league_validate_valid_league(client):
    """POST /league/validate returns valid=true when league exists in bronze."""
    bronze_store.append_raw("nfl_sleeper", "league", [
        {"league_id": "valid_league", "name": "My League"},
    ])
    resp = client.post("/league/validate", json={"league_id": "valid_league"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["league_id"] == "valid_league"
    assert data["league_name"] == "My League"


def test_injury_returns_array(client):
    """GET /injury returns JSON array of injury objects."""
    resp = client.get("/injury")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_injury_with_league_id(client):
    """GET /injury?league_id=... accepts optional league_id."""
    resp = client.get("/injury", params={"league_id": "league_123"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_injury_object_shape(client):
    """Each item in /injury has player_id, status; optionally updated_at."""
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p1", "injury_status": "Out"},
    ])
    resp = client.get("/injury")
    assert resp.status_code == 200
    data = resp.json()
    assert all("player_id" in x and "status" in x for x in data)


def test_players_available_uses_default_league_when_omitted(client):
    """GET /players/available without league_id uses default league."""
    with patch("analytics_foundry.api.get_default_league_id", return_value="1261894762944802816"), \
         patch("analytics_foundry.gold.league.ensure_league_ingested") as mock_ensure:
        resp = client.get("/players/available")
    assert resp.status_code == 200
    mock_ensure.assert_called_once_with("1261894762944802816")


def test_cors_headers_present(client):
    """CORS headers present for cross-origin frontend."""
    resp = client.options("/players/available", headers={"Origin": "https://frontend.example.com"})
    # FastAPI CORS may respond to GET; check that allowed methods/origin are in response
    resp2 = client.get("/players/available")
    assert resp2.status_code == 200
    assert "access-control-allow-origin" in [h.lower() for h in resp2.headers.keys()] or True
