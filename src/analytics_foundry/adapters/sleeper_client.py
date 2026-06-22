"""Thin client for Sleeper API. Inject a mock in tests to avoid network calls."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any

SLEEPER_BASE = "https://api.sleeper.app/v1"

_players_lock = threading.Lock()
_players_cache: tuple[float, dict[str, Any]] | None = None


def _cache_ttl_seconds() -> float:
    return float(os.environ.get("FOUNDRY_SLEEPER_CACHE_TTL_SECONDS", "3600"))


def _min_interval_seconds() -> float:
    return float(os.environ.get("FOUNDRY_SLEEPER_MIN_INTERVAL_SECONDS", "0"))


_last_request_mono = 0.0
_interval_lock = threading.Lock()


def _throttle() -> None:
    """Optional pause between HTTP calls to reduce burst rate (self-hosted politeness)."""
    gap = _min_interval_seconds()
    if gap <= 0:
        return
    global _last_request_mono
    with _interval_lock:
        now = time.monotonic()
        wait = gap - (now - _last_request_mono)
        if wait > 0:
            time.sleep(wait)
        _last_request_mono = time.monotonic()


def _fetch_json(url: str) -> Any:
    """HTTP GET and parse JSON (no rate limiting)."""
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _get(url: str) -> Any:
    _throttle()
    return _fetch_json(url)


def get_players_nfl() -> dict[str, Any]:
    """Fetch all NFL players (broad; not league-scoped). Returns dict player_id -> player."""
    global _players_cache
    ttl = _cache_ttl_seconds()
    now = time.monotonic()
    if ttl > 0:
        with _players_lock:
            if _players_cache is not None:
                ts, data = _players_cache
                if now - ts < ttl:
                    return data
    data = _get(f"{SLEEPER_BASE}/players/nfl")
    if ttl > 0:
        with _players_lock:
            _players_cache = (time.monotonic(), data)
    return data


def get_league(league_id: str) -> dict[str, Any] | None:
    """Fetch league by ID. Returns None if 404 or invalid."""
    try:
        return _get(f"{SLEEPER_BASE}/league/{league_id}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def get_rosters(league_id: str) -> list[dict[str, Any]]:
    """Fetch rosters for a league."""
    out = _get(f"{SLEEPER_BASE}/league/{league_id}/rosters")
    return out if isinstance(out, list) else []


def get_matchups(league_id: str, week: int = 1) -> list[dict[str, Any]]:
    """Fetch matchups for a league and week."""
    out = _get(f"{SLEEPER_BASE}/league/{league_id}/matchups/{week}")
    return out if isinstance(out, list) else []


def clear_players_cache() -> None:
    """Clear in-memory NFL players cache (tests or forced refresh)."""
    global _players_cache
    with _players_lock:
        _players_cache = None


def reset_request_throttle() -> None:
    """Reset min-interval throttle baseline (for tests)."""
    global _last_request_mono
    with _interval_lock:
        _last_request_mono = 0.0
