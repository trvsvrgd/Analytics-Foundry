"""Sleeper client cache and throttle (mocked HTTP)."""

import time
from unittest.mock import patch

import pytest

from analytics_foundry.adapters import sleeper_client as sc


@pytest.fixture(autouse=True)
def clear_cache():
    sc.clear_players_cache()
    sc.reset_request_throttle()
    yield
    sc.clear_players_cache()
    sc.reset_request_throttle()


def test_get_players_nfl_uses_cache_within_ttl(monkeypatch):
    monkeypatch.setenv("FOUNDRY_SLEEPER_CACHE_TTL_SECONDS", "60")
    calls = {"n": 0}

    def fake_get(url: str):
        calls["n"] += 1
        return {"1": {"display_name": "A"}}

    with patch.object(sc, "_fetch_json", side_effect=fake_get):
        a = sc.get_players_nfl()
        b = sc.get_players_nfl()
    assert a == b
    assert calls["n"] == 1


def test_get_players_nfl_bypass_cache_when_ttl_zero(monkeypatch):
    monkeypatch.setenv("FOUNDRY_SLEEPER_CACHE_TTL_SECONDS", "0")
    calls = {"n": 0}

    def fake_get(url: str):
        calls["n"] += 1
        return {"x": {}}

    with patch.object(sc, "_fetch_json", side_effect=fake_get):
        sc.get_players_nfl()
        sc.get_players_nfl()
    assert calls["n"] == 2


def test_min_interval_throttles(monkeypatch):
    monkeypatch.setenv("FOUNDRY_SLEEPER_MIN_INTERVAL_SECONDS", "0.05")
    monkeypatch.setenv("FOUNDRY_SLEEPER_CACHE_TTL_SECONDS", "0")
    with patch.object(sc, "_fetch_json", return_value={}):
        t0 = time.monotonic()
        sc.get_players_nfl()
        sc.get_players_nfl()
        elapsed = time.monotonic() - t0
    assert elapsed >= 0.04
