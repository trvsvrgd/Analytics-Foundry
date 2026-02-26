"""Gold: available players for API. Reads from silver; shapes per TECH_SPEC player object."""

from typing import Any, Dict, List, Optional

from analytics_foundry.silver import players as silver_players
from analytics_foundry.silver import rosters as silver_rosters


def _to_player_object(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Shape silver record to API player object: id, name, position, team, status, age, trending."""
    pid = rec.get("player_id")
    return {
        "id": str(pid) if pid is not None else "",
        "player_id": str(pid) if pid is not None else "",
        "name": str(rec.get("name") or ""),
        "position": str(rec.get("position") or ""),
        "team": str(rec.get("team") or ""),
        "status": str(rec.get("status") or ""),
        "age": rec.get("age"),
        "trending": rec.get("trending"),
    }


def get_available_players(league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return available (unrostered) players. If league_id given, exclude players on rosters in that league."""
    players_list = silver_players.get_players()
    if league_id:
        rostered_ids = silver_rosters.get_rostered_player_ids(league_id)
        players_list = [p for p in players_list if p["player_id"] not in rostered_ids]
    return [_to_player_object(p) for p in players_list]

