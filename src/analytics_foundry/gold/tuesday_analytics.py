"""Gold: Tuesday evening analytics models (Waiver Targets, Trade Regression, Injury Depth Cascade, Roster Utility, FAAB Bid Predictor)."""

from typing import Any, Dict, List, Optional
from analytics_foundry.silver import players as silver_players
from analytics_foundry.silver import rosters as silver_rosters
from analytics_foundry.silver import tuesday_analytics as silver_tuesday


def get_waiver_targets(league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Model 1 & 10: Identify priority waiver targets based on utilization breakouts."""
    stats = silver_tuesday.get_player_weekly_stats()
    stats_map = {s["player_id"]: s for s in stats}
    players = {p["player_id"]: p for p in silver_players.get_players()}
    
    rostered_ids = set()
    if league_id:
        rostered_ids = silver_rosters.get_rostered_player_ids(league_id)
        
    out = []
    for pid, p in players.items():
        if pid in rostered_ids:
            continue
            
        p_stats = stats_map.get(pid)
        if not p_stats:
            continue
            
        snap_growth = p_stats["snaps_pct"] - p_stats["snaps_pct_prev"]
        is_route_breakout = p_stats["routes_run_pct"] >= 0.80 and p_stats["targets"] <= 3
        is_snap_riser = snap_growth >= 0.15
        
        if not (is_route_breakout or is_snap_riser):
            continue
            
        # Recommendation scoring
        score = 50.0
        if is_snap_riser:
            score += snap_growth * 50.0
        if is_route_breakout:
            score += p_stats["routes_run_pct"] * 30.0
            
        reason = []
        if is_snap_riser:
            reason.append(f"Snap increase of {round(snap_growth * 100)}%")
        if is_route_breakout:
            reason.append(f"Route participation of {round(p_stats['routes_run_pct'] * 100)}% on low targets")
            
        out.append({
            "player_id": pid,
            "player_name": p["name"],
            "position": p["position"],
            "team": p["team"],
            "snaps_pct": p_stats["snaps_pct"],
            "snap_growth": round(snap_growth, 3),
            "routes_run_pct": p_stats["routes_run_pct"],
            "targets": p_stats["targets"],
            "recommendation_score": round(score, 1),
            "breakout_reason": " & ".join(reason),
        })
        
    return sorted(out, key=lambda x: x["recommendation_score"], reverse=True)


def get_trade_regression(league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Model 3 & 8: Compute Expected Fantasy Points (xFP) regression to flag buy-low and sell-high players."""
    stats = silver_tuesday.get_player_weekly_stats()
    stats_map = {s["player_id"]: s for s in stats}
    players = {p["player_id"]: p for p in silver_players.get_players()}
    
    rostered_ids = set()
    rosters = []
    if league_id:
        rosters = silver_rosters.get_rosters(league_id=league_id)
        rostered_ids = silver_rosters.get_rostered_player_ids(league_id)
        
    roster_owner_map = {}
    for r in rosters:
        for pid in (r.get("players") or []):
            roster_owner_map[pid] = r.get("roster_id")
            
    out = []
    for pid, p in players.items():
        if league_id and pid not in rostered_ids:
            continue
            
        p_stats = stats_map.get(pid)
        if not p_stats:
            continue
            
        actual = p_stats["actual_points"]
        expected = p_stats["expected_points"]
        diff = expected - actual
        tds = p_stats["touchdowns"]
        
        recommendation = "Hold"
        if diff >= 4.0:
            recommendation = "Buy-Low"
        elif diff <= -6.0 or tds >= 2:
            recommendation = "Sell-High"
            
        out.append({
            "player_id": pid,
            "player_name": p["name"],
            "position": p["position"],
            "team": p["team"],
            "roster_id": roster_owner_map.get(pid),
            "actual_points": actual,
            "expected_points": expected,
            "points_difference": round(diff, 1),
            "touchdowns": tds,
            "recommendation": recommendation,
        })
        
    return sorted(out, key=lambda x: abs(x["points_difference"]), reverse=True)


def get_injury_cascade(league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Model 2: SimulateDepth Chart cascade when a starting player is injured."""
    players = {p["player_id"]: p for p in silver_players.get_players()}
    depth_charts = silver_tuesday.get_depth_charts()
    depth_map = {(d["team"], d["position"]): d["players"] for d in depth_charts}
    
    rostered_ids = set()
    if league_id:
        rostered_ids = silver_rosters.get_rostered_player_ids(league_id)
        
    injured_starters = []
    for pid, p in players.items():
        if league_id and pid not in rostered_ids:
            continue
        status = p.get("injury_status") or ""
        if status in {"Out", "Doubtful", "IR"}:
            injured_starters.append(p)
            
    out = []
    for starter in injured_starters:
        team = str(starter.get("team") or "").upper()
        pos = str(starter.get("position") or "").upper()
        
        # Check depth chart
        depth_players = depth_map.get((team, pos)) or []
        if starter["player_id"] not in depth_players:
            continue
            
        idx = depth_players.index(starter["player_id"])
        # If there is a backup player downstream on the chart
        if idx + 1 < len(depth_players):
            backup_id = depth_players[idx + 1]
            backup_name = players.get(backup_id, {}).get("name", "Unknown Backup")
            
            # Reallocate workload: assume backup inherits 75% of starter's baseline value
            # Let's say baseline value is 12.0 for starting RBs, 10.0 for starting WRs
            base_workload = 12.0 if pos == "RB" else 10.0
            projected_gain = base_workload * 0.75
            
            out.append({
                "injured_player_id": starter["player_id"],
                "injured_player_name": starter["name"],
                "position": pos,
                "team": team,
                "backup_player_id": backup_id,
                "backup_player_name": backup_name,
                "projected_points_gain": round(projected_gain, 1),
            })
            
    return out


def get_roster_utility(league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Model 7: Audit bench players to identify holds, spot starters, and drop candidates."""
    if not league_id:
        return []
        
    rosters = silver_rosters.get_rosters(league_id=league_id)
    players = {p["player_id"]: p for p in silver_players.get_players()}
    depth_charts = silver_tuesday.get_depth_charts()
    depth_map = {(d["team"], d["position"]): d["players"] for d in depth_charts}
    
    stats = silver_tuesday.get_player_weekly_stats()
    stats_map = {s["player_id"]: s for s in stats}
    
    # Simple rule: starters are players with high snap rates, bench has lower snaps
    out = []
    for r in rosters:
        rid = r.get("roster_id")
        r_players = r.get("players") or []
        
        for pid in r_players:
            p = players.get(pid)
            if not p:
                continue
                
            p_stats = stats_map.get(pid, {"snaps_pct": 0.0, "expected_points": 0.0})
            snaps = p_stats["snaps_pct"]
            expected = p_stats["expected_points"]
            pos = str(p.get("position") or "").upper()
            team = str(p.get("team") or "").upper()
            
            # Check if this player is a backup on the depth chart
            depth_players = depth_map.get((team, pos)) or []
            is_handcuff = False
            if len(depth_players) > 1 and pid in depth_players[1:]:
                is_handcuff = True
                
            classification = "Bench Starter"
            if snaps >= 0.55:
                classification = "Core Starter"
            elif is_handcuff and pos == "RB":
                classification = "Must-Hold Handcuff"
            elif expected >= 8.0:
                classification = "Spot Starter"
            elif snaps <= 0.15 and expected <= 3.0 and not is_handcuff:
                classification = "Drop Candidate"
                
            out.append({
                "league_id": league_id,
                "roster_id": rid,
                "player_id": pid,
                "player_name": p["name"],
                "position": pos,
                "team": team,
                "snaps_pct": snaps,
                "expected_points": expected,
                "utility_classification": classification,
            })
            
    return out


def get_waiver_bids(league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Model 12: Predict waiver bidding ranges based on team needs and opponent budgets."""
    if not league_id:
        return []
        
    # Find top waiver targets
    targets = get_waiver_targets(league_id=league_id)[:3]
    faab = silver_tuesday.get_faab_history()
    faab_map = {f["roster_id"]: f for f in faab}
    
    rosters = silver_rosters.get_rosters(league_id=league_id)
    players = {p["player_id"]: p for p in silver_players.get_players()}
    
    out = []
    for target in targets:
        pos = target["position"]
        pid = target["player_id"]
        
        # Analyze needs: managers with low total trending points or injuries in that position
        needs = []
        for r in rosters:
            rid = r.get("roster_id")
            r_players = r.get("players") or []
            
            # Count players in target position
            pos_players = [players[p] for p in r_players if p in players and players[p].get("position") == pos]
            # If they have fewer than 3 players at position, they need it
            if len(pos_players) <= 2:
                needs.append(rid)
                
        # Calculate bid estimate
        bids = []
        for rid in needs:
            r_faab = faab_map.get(rid, {"remaining_faab": 100}).get("remaining_faab", 100)
            # Estimate bid: base bid is 5% of budget, max is 25% for high scoring breakouts
            bid_pct = 0.08 if target["recommendation_score"] >= 70 else 0.03
            estimated_bid = int(r_faab * bid_pct)
            bids.append({
                "roster_id": rid,
                "estimated_bid": max(2, estimated_bid),
                "remaining_faab": r_faab,
            })
            
        bids = sorted(bids, key=lambda x: x["estimated_bid"], reverse=True)
        winning_bid = bids[0]["estimated_bid"] if bids else 5
        runner_up = bids[1]["estimated_bid"] if len(bids) > 1 else 2
        
        out.append({
            "player_id": pid,
            "player_name": target["player_name"],
            "position": pos,
            "recommendation_score": target["recommendation_score"],
            "predicted_winning_bid": winning_bid,
            "predicted_runner_up_bid": runner_up,
            "bidding_rosters": bids,
        })
        
    return out
