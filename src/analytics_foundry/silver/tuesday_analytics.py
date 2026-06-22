"""Silver: conformed Tuesday evening analytics feed data (player weekly stats, depth charts, vegas weather, FAAB history)."""

from typing import Any, Dict, List
from analytics_foundry.bronze import store as bronze_store

NFL_WEEKLY_FEED = "nfl_weekly_feed"


def get_player_weekly_stats() -> List[Dict[str, Any]]:
    """Return conformed player weekly statistics."""
    raw = bronze_store.get_raw(NFL_WEEKLY_FEED, "player_weekly_stats")
    by_key = {}
    for rec in raw:
        pid = rec.get("player_id")
        week = rec.get("week") or 1
        if not pid:
            continue
        conformed = {
            "player_id": str(pid),
            "week": int(week),
            "snaps_pct": float(rec.get("snaps_pct") or 0.0),
            "snaps_pct_prev": float(rec.get("snaps_pct_prev") or 0.0),
            "routes_run_pct": float(rec.get("routes_run_pct") or 0.0),
            "targets": int(rec.get("targets") or 0),
            "carries": int(rec.get("carries") or 0),
            "actual_points": float(rec.get("actual_points") or 0.0),
            "expected_points": float(rec.get("expected_points") or 0.0),
            "touchdowns": int(rec.get("touchdowns") or 0),
        }
        by_key[(conformed["player_id"], conformed["week"])] = conformed
    return list(by_key.values())


def get_depth_charts() -> List[Dict[str, Any]]:
    """Return conformed team depth charts."""
    raw = bronze_store.get_raw(NFL_WEEKLY_FEED, "depth_charts")
    by_key = {}
    for rec in raw:
        team = rec.get("team")
        pos = rec.get("position")
        if not team or not pos:
            continue
        conformed = {
            "team": str(team).upper(),
            "position": str(pos).upper(),
            "players": [str(p) for p in (rec.get("players") or []) if p],
        }
        by_key[(conformed["team"], conformed["position"])] = conformed
    return list(by_key.values())


def _coerce_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if not val:
        return False
    s = str(val).strip().lower()
    return s in {"true", "1", "yes"}


def get_vegas_weather() -> List[Dict[str, Any]]:
    """Return conformed vegas odds and weather details."""
    raw = bronze_store.get_raw(NFL_WEEKLY_FEED, "vegas_weather")
    by_key = {}
    for rec in raw:
        home = rec.get("home_team")
        away = rec.get("away_team")
        if not home or not away:
            continue
        conformed = {
            "home_team": str(home).upper(),
            "away_team": str(away).upper(),
            "over_under": float(rec.get("over_under") or 0.0),
            "implied_total_home": float(rec.get("implied_total_home") or 0.0),
            "implied_total_away": float(rec.get("implied_total_away") or 0.0),
            "wind_speed": int(rec.get("wind_speed") or 0),
            "is_dome": _coerce_bool(rec.get("is_dome", False)),
            "weather_summary": str(rec.get("weather_summary") or ""),
        }
        by_key[(conformed["home_team"], conformed["away_team"])] = conformed
    return list(by_key.values())


def get_faab_history() -> List[Dict[str, Any]]:
    """Return conformed league FAAB and bid history."""
    raw = bronze_store.get_raw(NFL_WEEKLY_FEED, "faab_history")
    by_key = {}
    for rec in raw:
        rid = rec.get("roster_id")
        if rid is None:
            continue
        history = []
        for bid in (rec.get("bid_history") or []):
            history.append({
                "player_id": str(bid.get("player_id") or ""),
                "bid": int(bid.get("bid") or 0),
                "success": _coerce_bool(bid.get("success", False)),
            })
        conformed = {
            "roster_id": int(rid),
            "remaining_faab": int(rec.get("remaining_faab") or 100),
            "bid_history": history,
        }
        by_key[conformed["roster_id"]] = conformed
    return list(by_key.values())
