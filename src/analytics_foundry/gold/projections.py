"""Gold: custom NFL matchup win probabilities and team defense projections."""

from typing import Any, Dict, List, Optional
from analytics_foundry.silver import players as silver_players
from analytics_foundry.silver import rosters as silver_rosters
from analytics_foundry.silver import projections as silver_projections
from analytics_foundry.bronze import store as bronze_store

NFL_SLEEPER = "nfl_sleeper"


def _get_team_opponent_info(team: str, matchups: List[Dict[str, Any]]) -> tuple[Optional[str], bool]:
    """Find the opponent and whether they are playing a backup QB for a given team."""
    team_upper = team.upper()
    for m in matchups:
        home = str(m.get("home_team") or "").upper()
        away = str(m.get("away_team") or "").upper()
        if home == team_upper:
            return away, bool(m.get("away_qb_backup", False))
        if away == team_upper:
            return home, bool(m.get("home_qb_backup", False))
    return None, False


def _get_projected_defense_points(
    team: str,
    matchups: List[Dict[str, Any]],
    stats_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Calculate projected points for a defense based on opponent, rankings, and backup QB."""
    team_upper = team.upper()
    opponent, backup_qb = _get_team_opponent_info(team_upper, matchups)
    
    # Retrieve stats or fallback to defaults
    def_stats = stats_map.get(team_upper, {"defensive_rank": 16, "historical_win_rate": 0.5})
    def_rank = def_stats.get("defensive_rank", 16)
    
    if opponent:
        opp_stats = stats_map.get(opponent, {"offensive_rank": 16})
        opp_off_rank = opp_stats.get("offensive_rank", 16)
    else:
        opponent = "BYE"
        opp_off_rank = 16
        backup_qb = False

    # Base points
    base_points = 10.0
    
    # Adjust by opponent offensive rank (worst offense rank 32 adds points, best rank 1 subtracts)
    opp_adjustment = (opp_off_rank - 16) * 0.5
    
    # Adjust by own defensive rank (best defense rank 1 adds points, worst rank 32 subtracts)
    def_adjustment = (16 - def_rank) * 0.3
    
    # Backup QB bonus
    qb_bonus = 5.0 if backup_qb else 0.0
    
    proj_points = base_points + opp_adjustment + def_adjustment + qb_bonus
    
    return {
        "team": team_upper,
        "opponent": opponent,
        "defensive_rank": def_rank,
        "opponent_offensive_rank": opp_off_rank,
        "backup_qb_playing": backup_qb,
        "projected_points": round(proj_points, 2),
    }


def get_defense_projections(league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return team defense projections. If league_id given, filter/annotate for league rosters."""
    matchups = silver_projections.get_weekly_matchups()
    stats = silver_projections.get_team_stats()
    stats_map = {s["team"]: s for s in stats}
    
    # Pre-calculate projections for all known teams
    all_teams = set(stats_map.keys())
    for m in matchups:
        if m.get("home_team"):
            all_teams.add(str(m["home_team"]).upper())
        if m.get("away_team"):
            all_teams.add(str(m["away_team"]).upper())
            
    projs = {
        team: _get_projected_defense_points(team, matchups, stats_map)
        for team in all_teams
    }
    
    if not league_id:
        return sorted(projs.values(), key=lambda x: x["projected_points"], reverse=True)
        
    # If league_id given, map to rosters
    rosters = silver_rosters.get_rosters(league_id=league_id)
    players_map = {p["player_id"]: p for p in silver_players.get_players()}
    
    out = []
    for r in rosters:
        roster_id = r.get("roster_id")
        r_players = r.get("players") or []
        
        # Find starting defense players (position == DEF)
        defenses = [players_map[pid] for pid in r_players if pid in players_map and players_map[pid].get("position") == "DEF"]
        
        for d in defenses:
            team = str(d.get("team") or "").upper()
            proj = projs.get(team) or {
                "team": team,
                "opponent": "UNKNOWN",
                "defensive_rank": 16,
                "opponent_offensive_rank": 16,
                "backup_qb_playing": False,
                "projected_points": 10.0,
            }
            out.append({
                "league_id": league_id,
                "roster_id": roster_id,
                "player_id": d["player_id"],
                "player_name": d["name"],
                **proj,
            })
            
    return sorted(out, key=lambda x: x["projected_points"], reverse=True)


def get_win_probability(league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return win probability projections for the upcoming matchups in the given league."""
    if not league_id:
        return []
        
    # Load matchups from sleeper bronze store
    raw_matchups = bronze_store.get_raw(NFL_SLEEPER, "matchups")
    raw_matchups = [m for m in raw_matchups if str(m.get("league_id")) == str(league_id)]
    
    if not raw_matchups:
        return []
        
    # Group by matchup_id
    by_matchup: Dict[int, List[Dict[str, Any]]] = {}
    for m in raw_matchups:
        mid = m.get("matchup_id")
        if mid is None:
            continue
        by_matchup.setdefault(int(mid), []).append(m)
        
    # Load projections and player details
    def_projs = get_defense_projections(league_id=league_id)
    def_map = {d["roster_id"]: d["projected_points"] for d in def_projs if "roster_id" in d}
    
    players_map = {p["player_id"]: p for p in silver_players.get_players()}
    
    out = []
    for mid, rosters in by_matchup.items():
        if len(rosters) < 2:
            continue
        # We only support head-to-head matchup pairing
        m_a = rosters[0]
        m_b = rosters[1]
        
        rid_a = m_a.get("roster_id")
        rid_b = m_b.get("roster_id")
        
        # Calculate defense score adjustment
        proj_a = def_map.get(rid_a, 10.0)
        proj_b = def_map.get(rid_b, 10.0)
        
        # Roster trending strength sum
        players_a = m_a.get("players") or []
        players_b = m_b.get("players") or []
        
        trend_a = sum(float(players_map[p].get("trending") or 0.0) for p in players_a if p in players_map)
        trend_b = sum(float(players_map[p].get("trending") or 0.0) for p in players_b if p in players_map)
        
        # Win probability base formula
        diff = (trend_a - trend_b) * 0.1 + (proj_a - proj_b) * 0.02
        prob_a = 0.50 + diff
        prob_a = max(0.10, min(0.90, prob_a))
        prob_b = 1.0 - prob_a
        
        out.append({
            "league_id": league_id,
            "matchup_id": mid,
            "roster_id_a": rid_a,
            "roster_id_b": rid_b,
            "trending_a": round(trend_a, 2),
            "trending_b": round(trend_b, 2),
            "defense_proj_a": proj_a,
            "defense_proj_b": proj_b,
            "win_probability_a": round(prob_a, 4),
            "win_probability_b": round(prob_b, 4),
        })
        
    return out
