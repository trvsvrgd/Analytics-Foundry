"""Silver: injury report derived from silver players. Canonical schema: player_id, status, updated_at."""

from typing import Any, Dict, List

from analytics_foundry.silver import players as silver_players

# Canonical silver schema: player_id, status, updated_at
SILVER_INJURY_KEYS = ("player_id", "status", "updated_at")


def get_injuries() -> List[Dict[str, Any]]:
    """Return silver injuries: players with non-empty injury_status (excluding 'Active')."""
    players = silver_players.get_players()
    out: List[Dict[str, Any]] = []
    for p in players:
        status = p.get("injury_status") or p.get("status") or ""
        if not status or status == "Active":
            continue
        out.append({
            "player_id": p["player_id"],
            "status": str(status),
            "updated_at": p.get("updated_at"),
        })
    return out
