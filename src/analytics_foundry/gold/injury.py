"""Gold: injury report for API. Reads from bronze; TECH_SPEC shape: player_id, status, updated_at?."""

from typing import Any, Dict, List, Optional

from analytics_foundry.bronze import store as bronze_store

NFL_SLEEPER = "nfl_sleeper"


def get_injury_report(league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return injury report: list of {player_id, status, updated_at?}. Stub: no injury in bronze yet."""
    raw = bronze_store.get_raw(NFL_SLEEPER, "players")
    # Stub: if player has injury_status or status, include; else empty
    out = []
    for r in raw:
        pid = r.get("player_id") or r.get("id")
        status = r.get("injury_status") or r.get("status") or ""
        if not status or status == "Active":
            continue
        updated_at = r.get("updated_at") or r.get("injury_updated")
        out.append({
            "player_id": str(pid) if pid is not None else "",
            "status": str(status),
            **({"updated_at": str(updated_at)} if updated_at is not None else {}),
        })
    return out

