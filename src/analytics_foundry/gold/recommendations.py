"""Gold: waiver/add recommendations. Returns available players with a simple score for ranking."""

from typing import Any, Dict, List, Optional

from analytics_foundry.gold import players as gold_players


def get_waiver_recommendations(league_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Return waiver/add recommendations: available players with score (stub: trending or 0)."""
    available = gold_players.get_available_players(league_id=league_id)
    out = []
    for p in available[:limit]:
        score = p.get("trending")
        if score is None:
            score = 0.0
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0.0
        out.append({
            "player_id": p.get("id") or p.get("player_id"),
            "name": p.get("name"),
            "position": p.get("position"),
            "team": p.get("team"),
            "score": score,
        })
    return out
