"""Tests for Foundry Admin API: tables, transformations, ingest (with mocks), runs stub."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from analytics_foundry.api import app
from analytics_foundry.bronze import store as bronze_store


@pytest.fixture
def client():
    """TestClient with league/adapter mocks to avoid real Sleeper API calls."""
    with patch("analytics_foundry.gold.league.ensure_league_ingested", lambda _: None), \
         patch("analytics_foundry.admin_routes.get_adapter") as mock_get:
        adapter = type("MockAdapter", (), {"ingest_to_bronze": lambda self, **kw: None})()
        mock_get.return_value = adapter
        yield TestClient(app)


@pytest.fixture(autouse=True)
def clear_bronze():
    bronze_store.clear()
    yield
    bronze_store.clear()


def test_admin_tables_returns_layers(client):
    """GET /admin/tables returns bronze, silver, gold lists."""
    resp = client.get("/admin/tables")
    assert resp.status_code == 200
    data = resp.json()
    assert "bronze" in data
    assert "silver" in data
    assert "gold" in data
    assert isinstance(data["bronze"], list)
    assert isinstance(data["silver"], list)
    assert isinstance(data["gold"], list)


def test_admin_tables_bronze_list(client):
    """Bronze tables from store appear in list with row_count."""
    bronze_store.append_raw("nfl_sleeper", "players", [{"id": "1"}, {"id": "2"}])
    bronze_store.append_raw("nfl_sleeper", "league", [{"league_id": "x"}])
    resp = client.get("/admin/tables")
    assert resp.status_code == 200
    bronze = resp.json()["bronze"]
    assert len(bronze) == 2
    by_key = {(b["source_id"], b["table"]): b["row_count"] for b in bronze}
    assert by_key.get(("nfl_sleeper", "players")) == 2
    assert by_key.get(("nfl_sleeper", "league")) == 1


def test_admin_tables_sample_bronze(client):
    """GET /admin/tables/bronze/{source_id}/{table} returns sample rows."""
    bronze_store.append_raw("nfl_sleeper", "players", [
        {"player_id": "p1", "name": "A"},
        {"player_id": "p2", "name": "B"},
    ])
    resp = client.get("/admin/tables/bronze/nfl_sleeper/players")
    assert resp.status_code == 200
    data = resp.json()
    assert data["layer"] == "bronze"
    assert data["source_id"] == "nfl_sleeper"
    assert data["table"] == "players"
    assert len(data["rows"]) == 2
    assert data["rows"][0]["player_id"] == "p1"


def test_admin_tables_sample_gold(client):
    """GET /admin/tables/gold/available_players returns sample from gold getter."""
    bronze_store.append_raw("nfl_sleeper", "players", [{"player_id": "p1", "display_name": "X"}])
    resp = client.get("/admin/tables/gold/available_players")
    assert resp.status_code == 200
    data = resp.json()
    assert data["layer"] == "gold"
    assert data["name"] == "available_players"
    assert "rows" in data
    assert len(data["rows"]) >= 1


def test_admin_tables_sample_gold_injury(client):
    """GET /admin/tables/gold/injury returns sample from injury getter."""
    resp = client.get("/admin/tables/gold/injury")
    assert resp.status_code == 200
    data = resp.json()
    assert data["layer"] == "gold"
    assert data["name"] == "injury"


def test_admin_transform_list(client):
    """GET /admin/transformations returns layers with SQL file names."""
    resp = client.get("/admin/transformations")
    assert resp.status_code == 200
    data = resp.json()
    for layer in ("bronze", "silver", "gold"):
        assert layer in data
        assert isinstance(data[layer], list)


def test_admin_transform_get(client):
    """GET /admin/transformations/{layer}/{name} returns SQL content."""
    resp = client.get("/admin/transformations/bronze/nfl_sleeper_players")
    assert resp.status_code == 200
    data = resp.json()
    assert data["layer"] == "bronze"
    assert data["name"] == "nfl_sleeper_players"
    assert "sql" in data
    assert isinstance(data["sql"], str)


def test_admin_transform_not_found(client):
    """GET /admin/transformations with missing name returns 404."""
    resp = client.get("/admin/transformations/bronze/nonexistent_file_xyz")
    assert resp.status_code == 404


def test_admin_runs_returns_list(client):
    """GET /admin/runs returns list (stub)."""
    resp = client.get("/admin/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_admin_ingest_league(client):
    """POST /admin/ingest/league calls ensure_league_ingested and records run."""
    resp = client.post("/admin/ingest/league", json={"league_id": "league_abc"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "league_id": "league_abc"}
    runs = client.get("/admin/runs").json()
    assert len(runs) >= 1
    assert runs[0]["kind"] == "league"
    assert runs[0]["league_id"] == "league_abc"


def test_admin_ingest_broad(client):
    """POST /admin/ingest/broad calls adapter.ingest_to_bronze and records run."""
    resp = client.post("/admin/ingest/broad")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    runs = client.get("/admin/runs").json()
    assert any(r["kind"] == "broad" for r in runs)


def test_admin_ingest_broad_no_adapter():
    """POST /admin/ingest/broad returns 503 when adapter not registered."""
    with patch("analytics_foundry.admin_routes.get_adapter", return_value=None):
        c = TestClient(app)
        resp = c.post("/admin/ingest/broad")
    assert resp.status_code == 503


def test_admin_validate_league(client):
    """GET /admin/league/validate?league_id=... returns validate result."""
    bronze_store.append_raw("nfl_sleeper", "league", [
        {"league_id": "L1", "name": "Test League"},
    ])
    resp = client.get("/admin/league/validate", params={"league_id": "L1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["league_id"] == "L1"
    assert data["league_name"] == "Test League"


def test_admin_ui_served(client):
    """GET /admin and GET /admin/ serve HTML."""
    resp = client.get("/admin")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert b"Foundry Admin" in resp.content
    resp2 = client.get("/admin/")
    assert resp2.status_code == 200
    assert b"Foundry Admin" in resp2.content
