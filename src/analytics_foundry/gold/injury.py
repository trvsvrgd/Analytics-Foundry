"""Gold: injury report for API. Reads from silver; TECH_SPEC shape: player_id, status, updated_at?."""

from typing import Any, Dict, List, Optional

from analytics_foundry.silver import injuries as silver_injuries


def get_injury_report(league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return injury report: list of {player_id, status, updated_at?} from silver injuries."""
    injuries_list = silver_injuries.get_injuries()
    out = []
    for r in injuries_list:
        rec = {"player_id": r["player_id"], "status": r["status"]}
        if r.get("updated_at") is not None:
            rec["updated_at"] = str(r["updated_at"])
        out.append(rec)
    return out

