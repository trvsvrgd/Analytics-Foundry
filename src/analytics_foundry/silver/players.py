"""Silver: cleaned, conformed players. Canonical schema; dedup by player_id (latest wins)."""

from typing import Any, Dict, List

from analytics_foundry.bronze import store as bronze_store

NFL_SLEEPER = "nfl_sleeper"

# Canonical silver schema: player_id, name, position, team, status, injury_status, age, trending, updated_at
SILVER_PLAYER_KEYS = ("player_id", "name", "position", "team", "status", "injury_status", "age", "trending", "updated_at")


def _coerce_int(val: Any) -> int | None:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _coerce_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _to_silver_player(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Transform raw bronze record to canonical silver player schema."""
    pid = rec.get("player_id") or rec.get("id")
    if pid is None:
        return {}
    return {
        "player_id": str(pid),
        "name": str(rec.get("display_name") or rec.get("name") or ""),
        "position": str(rec.get("position") or ""),
        "team": str(rec.get("team") or ""),
        "status": str(rec.get("status") or ""),
        "injury_status": str(rec.get("injury_status") or ""),
        "age": _coerce_int(rec.get("age")),
        "trending": _coerce_float(rec.get("trending")),
        "updated_at": rec.get("updated_at") or rec.get("injury_updated"),
    }


def get_players() -> List[Dict[str, Any]]:
    """Return silver players: cleaned, deduplicated by player_id (latest record wins)."""
    raw = bronze_store.get_raw(NFL_SLEEPER, "players")
    by_id: Dict[str, Dict[str, Any]] = {}
    for rec in raw:
        silver = _to_silver_player(rec)
        if not silver:
            continue
        pid = silver["player_id"]
        by_id[pid] = silver
    return list(by_id.values())
