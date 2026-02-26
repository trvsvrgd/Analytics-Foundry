"""Silver: cleaned, conformed leagues. Canonical schema; dedup by league_id (latest wins)."""

from typing import Any, Dict, List, Optional

from analytics_foundry.bronze import store as bronze_store

NFL_SLEEPER = "nfl_sleeper"

# Canonical silver schema: league_id, name
SILVER_LEAGUE_KEYS = ("league_id", "name")


def _to_silver_league(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Transform raw bronze record to canonical silver league schema."""
    lid = rec.get("league_id")
    if not lid:
        return {}
    return {
        "league_id": str(lid),
        "name": str(rec.get("name") or rec.get("league_name") or ""),
    }


def get_leagues() -> List[Dict[str, Any]]:
    """Return silver leagues: cleaned, deduplicated by league_id (latest wins)."""
    raw = bronze_store.get_raw(NFL_SLEEPER, "league")
    by_id: Dict[str, Dict[str, Any]] = {}
    for rec in raw:
        silver = _to_silver_league(rec)
        if not silver:
            continue
        lid = silver["league_id"]
        by_id[lid] = silver
    return list(by_id.values())


def get_league(league_id: str) -> Optional[Dict[str, Any]]:
    """Return single silver league by league_id, or None if not found."""
    for lg in get_leagues():
        if lg["league_id"] == league_id:
            return lg
    return None
