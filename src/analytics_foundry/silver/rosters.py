"""Silver: cleaned, conformed rosters. Canonical schema; dedup by (league_id, roster_id) (latest wins)."""

from typing import Any, Dict, List

from analytics_foundry.bronze import store as bronze_store

NFL_SLEEPER = "nfl_sleeper"

# Canonical silver schema: league_id, roster_id, players (list of player_ids)
SILVER_ROSTER_KEYS = ("league_id", "roster_id", "players")


def _to_silver_roster(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Transform raw bronze record to canonical silver roster schema."""
    lid = rec.get("league_id")
    rid = rec.get("roster_id")
    if lid is None or rid is None:
        return {}
    players_raw = rec.get("players") or []
    players = [str(p) for p in players_raw if p is not None]
    return {
        "league_id": str(lid),
        "roster_id": rid if isinstance(rid, int) else str(rid),
        "players": players,
    }


def get_rosters(league_id: str | None = None) -> List[Dict[str, Any]]:
    """Return silver rosters. If league_id given, filter to that league. Dedup by (league_id, roster_id)."""
    raw = bronze_store.get_raw(NFL_SLEEPER, "rosters")
    by_key: Dict[tuple, Dict[str, Any]] = {}
    for rec in raw:
        silver = _to_silver_roster(rec)
        if not silver:
            continue
        lid = silver["league_id"]
        if league_id is not None and lid != league_id:
            continue
        key = (lid, str(silver["roster_id"]))
        by_key[key] = silver
    return list(by_key.values())


def get_rostered_player_ids(league_id: str) -> set[str]:
    """Return set of player_ids that are on rosters in the given league."""
    ids: set[str] = set()
    for r in get_rosters(league_id=league_id):
        ids.update(r.get("players") or [])
    return ids
