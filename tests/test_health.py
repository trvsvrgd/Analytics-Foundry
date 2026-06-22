"""Health, readiness, and metrics endpoints."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from analytics_foundry.api import app
from analytics_foundry.health import get_readiness


def test_get_readiness_false_without_adapter():
    """Patch health module binding (import-time copy of get_adapter)."""
    with patch("analytics_foundry.health.get_adapter", return_value=None):
        body = get_readiness()
    assert body["ready"] is False


def test_health_ok():
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_ready_ok():
    with TestClient(app) as client:
        r = client.get("/ready")
    assert r.status_code == 200
    assert r.json().get("ready") is True


def test_metrics_disabled_by_default():
    with TestClient(app) as client:
        r = client.get("/metrics")
    assert r.status_code == 404


def test_metrics_when_enabled(monkeypatch):
    monkeypatch.setenv("FOUNDRY_PROMETHEUS", "1")
    with TestClient(app) as client:
        r = client.get("/metrics")
    assert r.status_code == 200
    assert "foundry_http_requests_total" in r.text
