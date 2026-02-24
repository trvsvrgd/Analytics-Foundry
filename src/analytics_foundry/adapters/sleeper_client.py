"""Thin client for Sleeper API. Inject a mock in tests to avoid network calls."""

import json
import urllib.request
from typing import Any, Dict, List, Optional

SLEEPER_BASE = "https://api.sleeper.app/v1"


def _get(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode())


def get_players_nfl() -> Dict[str, Any]:
    """Fetch all NFL players (broad; not league-scoped). Returns dict player_id -> player."""
    return _get(f"{SLEEPER_BASE}/players/nfl")


def get_league(league_id: str) -> Optional[Dict[str, Any]]:
    """Fetch league by ID. Returns None if 404 or invalid."""
    try:
        return _get(f"{SLEEPER_BASE}/league/{league_id}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def get_rosters(league_id: str) -> List[Dict[str, Any]]:
    """Fetch rosters for a league."""
    out = _get(f"{SLEEPER_BASE}/league/{league_id}/rosters")
    return out if isinstance(out, list) else []


def get_matchups(league_id: str, week: int = 1) -> List[Dict[str, Any]]:
    """Fetch matchups for a league and week."""
    out = _get(f"{SLEEPER_BASE}/league/{league_id}/matchups/{week}")
    return out if isinstance(out, list) else []
