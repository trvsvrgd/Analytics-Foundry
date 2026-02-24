"""Gold: available players for API. Reads from bronze; shapes per TECH_SPEC player object."""

from typing import Any, Dict, List, Optional

from analytics_foundry.bronze import store as bronze_store

NFL_SLEEPER = "nfl_sleeper"


def _to_player_object(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Shape bronze record to API player object: id, name, position, team, status, age, trending."""
    pid = rec.get("player_id") or rec.get("id")
    name = rec.get("name") or rec.get("display_name") or ""
    position = rec.get("position") or ""
    team = rec.get("team") or ""
    status = rec.get("status") or ""
    age = rec.get("age")
    if age is not None and not isinstance(age, (int, float)):
        try:
            age = int(age) if age else None
        except (TypeError, ValueError):
            age = None
    trending = rec.get("trending")
    if trending is not None and not isinstance(trending, (int, float)):
        try:
            trending = float(trending) if trending else None
        except (TypeError, ValueError):
            trending = None
    return {
        "id": str(pid) if pid is not None else "",
        "player_id": str(pid) if pid is not None else "",
        "name": str(name),
        "position": str(position),
        "team": str(team),
        "status": str(status),
        "age": age,
        "trending": trending,
    }


def get_available_players(league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return available (unrostered) players. If league_id given, exclude players on rosters in that league."""
    raw = bronze_store.get_raw(NFL_SLEEPER, "players")
    if league_id:
        rosters = bronze_store.get_raw(NFL_SLEEPER, "rosters")
        rostered_ids = set()
        for r in rosters:
            if r.get("league_id") != league_id:
                continue
            # Sleeper roster has 'players' list of player_ids
            for pid in r.get("players") or []:
                rostered_ids.add(str(pid))
        raw = [p for p in raw if str(p.get("player_id") or p.get("id") or "") not in rostered_ids]
    return [_to_player_object(p) for p in raw]

