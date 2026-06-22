"""Gold data product: fantasy manager brief assembled from recommendation models."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from analytics_foundry.gold import projections as gold_projections
from analytics_foundry.gold import recommendations as gold_recommendations
from analytics_foundry.gold import tuesday_analytics as gold_tuesday


def get_manager_brief(league_id: Optional[str] = None, limit: int = 12) -> Dict[str, Any]:
    """Return a compact fantasy-manager insight bundle for downstream apps."""
    safe_limit = max(1, min(int(limit or 12), 50))
    waiver_recommendations = gold_recommendations.get_waiver_recommendations(
        league_id=league_id,
        limit=safe_limit,
    )
    waiver_targets = gold_tuesday.get_waiver_targets(league_id=league_id)[:safe_limit]
    waiver_bids = gold_tuesday.get_waiver_bids(league_id=league_id)[:safe_limit]
    trade_regression = gold_tuesday.get_trade_regression(league_id=league_id)[:safe_limit]
    injury_cascade = gold_tuesday.get_injury_cascade(league_id=league_id)[:safe_limit]
    roster_utility = gold_tuesday.get_roster_utility(league_id=league_id)[:safe_limit]
    defense_projections = gold_projections.get_defense_projections(league_id=league_id)[:safe_limit]
    win_probability = gold_projections.get_win_probability(league_id=league_id)[:safe_limit]

    priority_actions = _build_priority_actions(
        waiver_targets=waiver_targets,
        waiver_bids=waiver_bids,
        trade_regression=trade_regression,
        injury_cascade=injury_cascade,
        roster_utility=roster_utility,
        defense_projections=defense_projections,
        win_probability=win_probability,
        limit=safe_limit,
    )

    trade_signals = [r for r in trade_regression if r.get("recommendation") in {"Buy-Low", "Sell-High"}]
    drop_candidates = [r for r in roster_utility if r.get("utility_classification") == "Drop Candidate"]

    return {
        "league_id": league_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": {
            "priority_actions": len(priority_actions),
            "waiver_targets": len(waiver_targets),
            "injury_risks": len(injury_cascade),
            "trade_signals": len(trade_signals),
            "drop_candidates": len(drop_candidates),
            "lineup_edges": len(defense_projections) + len(win_probability),
        },
        "priority_actions": priority_actions,
        "models": {
            "waiver_recommendations": waiver_recommendations,
            "waiver_targets": waiver_targets,
            "waiver_bids": waiver_bids,
            "trade_regression": trade_regression,
            "injury_cascade": injury_cascade,
            "roster_utility": roster_utility,
            "defense_projections": defense_projections,
            "win_probability": win_probability,
        },
    }


def _build_priority_actions(
    waiver_targets: List[Dict[str, Any]],
    waiver_bids: List[Dict[str, Any]],
    trade_regression: List[Dict[str, Any]],
    injury_cascade: List[Dict[str, Any]],
    roster_utility: List[Dict[str, Any]],
    defense_projections: List[Dict[str, Any]],
    win_probability: List[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    bid_by_player = {str(b.get("player_id")): b for b in waiver_bids if b.get("player_id") is not None}
    actions: List[Dict[str, Any]] = []

    for target in waiver_targets[:5]:
        player_id = str(target.get("player_id") or "")
        bid = bid_by_player.get(player_id, {})
        score = _num(target.get("recommendation_score"))
        bid_value = bid.get("predicted_winning_bid")
        bid_text = f" with a ${bid_value} FAAB bid" if bid_value is not None else ""
        actions.append(
            _action(
                action_id=f"waiver-{player_id or len(actions)}",
                category="Waiver",
                urgency="Now",
                title=f"Add {target.get('player_name') or target.get('name') or 'waiver target'}",
                recommendation=f"Place a waiver claim{bid_text}.",
                rationale=str(target.get("breakout_reason") or "Ranks highly in the waiver target model."),
                impact_score=score,
                confidence=_confidence(score, high=80, medium=60),
                source_model="tuesday_waiver_targets",
                player_name=target.get("player_name"),
                position=target.get("position"),
                team=target.get("team"),
                estimated_bid=bid_value,
            )
        )

    for cascade in injury_cascade[:4]:
        gain = _num(cascade.get("projected_points_gain"))
        backup_name = cascade.get("backup_player_name") or "backup"
        injured_name = cascade.get("injured_player_name") or "injured starter"
        actions.append(
            _action(
                action_id=f"injury-{cascade.get('backup_player_id') or len(actions)}",
                category="Injury",
                urgency="Now",
                title=f"Cover {injured_name}",
                recommendation=f"Prioritize {backup_name} as the direct replacement.",
                rationale=f"Depth cascade projects a {gain:.1f} point workload gain.",
                impact_score=70 + gain,
                confidence=_confidence(gain, high=8, medium=4),
                source_model="tuesday_injury_cascade",
                player_name=backup_name,
                position=cascade.get("position"),
                team=cascade.get("team"),
            )
        )

    for signal in trade_regression[:6]:
        recommendation = signal.get("recommendation")
        if recommendation not in {"Buy-Low", "Sell-High"}:
            continue
        diff = _num(signal.get("points_difference"))
        player_name = signal.get("player_name") or "trade candidate"
        verb = "Send an offer for" if recommendation == "Buy-Low" else "Shop"
        actions.append(
            _action(
                action_id=f"trade-{signal.get('player_id') or len(actions)}",
                category="Trade",
                urgency="This week",
                title=f"{recommendation}: {player_name}",
                recommendation=f"{verb} {player_name}.",
                rationale=f"Expected points gap is {diff:+.1f}; actual production is likely to regress.",
                impact_score=55 + abs(diff),
                confidence=_confidence(abs(diff), high=8, medium=4),
                source_model="tuesday_trade_regression",
                player_name=player_name,
                position=signal.get("position"),
                team=signal.get("team"),
            )
        )

    for utility in roster_utility[:8]:
        if utility.get("utility_classification") != "Drop Candidate":
            continue
        player_name = utility.get("player_name") or "bench player"
        expected = _num(utility.get("expected_points"))
        actions.append(
            _action(
                action_id=f"drop-{utility.get('player_id') or len(actions)}",
                category="Roster",
                urgency="Before waivers",
                title=f"Drop candidate: {player_name}",
                recommendation=f"Use {player_name} as the first cut for waiver claims.",
                rationale=f"Bench utility model shows {expected:.1f} expected points with low usage.",
                impact_score=48 + max(0.0, 6.0 - expected),
                confidence=_confidence(max(0.0, 6.0 - expected), high=5, medium=2),
                source_model="tuesday_roster_utility",
                player_name=player_name,
                position=utility.get("position"),
                team=utility.get("team"),
            )
        )

    for defense in defense_projections[:4]:
        points = _num(defense.get("projected_points"))
        if points < 14:
            continue
        team = defense.get("team") or defense.get("player_name") or "defense"
        opponent = defense.get("opponent") or "opponent"
        actions.append(
            _action(
                action_id=f"defense-{team}",
                category="Lineup",
                urgency="This week",
                title=f"Stream {team} defense",
                recommendation=f"Start or claim {team} against {opponent}.",
                rationale=f"Defense model projects {points:.1f} points.",
                impact_score=45 + points,
                confidence=_confidence(points, high=18, medium=14),
                source_model="defense_projections",
                team=team,
            )
        )

    for matchup in win_probability[:3]:
        probability = min(
            _num(matchup.get("win_probability_a")),
            _num(matchup.get("win_probability_b")),
        )
        if probability <= 0 or probability > 0.45:
            continue
        matchup_id = matchup.get("matchup_id") or len(actions)
        actions.append(
            _action(
                action_id=f"matchup-{matchup_id}",
                category="Matchup",
                urgency="This week",
                title=f"Underdog matchup {matchup_id}",
                recommendation="Look for one high-upside lineup change before kickoff.",
                rationale=f"Win probability model shows a {probability:.0%} lower-side outcome.",
                impact_score=50 + (0.45 - probability) * 100,
                confidence=_confidence(0.45 - probability, high=0.15, medium=0.05),
                source_model="win_probability",
            )
        )

    actions.sort(key=lambda item: (-_urgency_rank(item["urgency"]), -_num(item["impact_score"]), item["title"]))
    return actions[:limit]


def _action(
    *,
    action_id: str,
    category: str,
    urgency: str,
    title: str,
    recommendation: str,
    rationale: str,
    impact_score: float,
    confidence: str,
    source_model: str,
    player_name: Any = None,
    position: Any = None,
    team: Any = None,
    estimated_bid: Any = None,
) -> Dict[str, Any]:
    action = {
        "id": action_id,
        "category": category,
        "urgency": urgency,
        "title": title,
        "recommendation": recommendation,
        "rationale": rationale,
        "impact_score": round(float(impact_score), 1),
        "confidence": confidence,
        "source_model": source_model,
    }
    if player_name:
        action["player_name"] = player_name
    if position:
        action["position"] = position
    if team:
        action["team"] = team
    if estimated_bid is not None:
        action["estimated_bid"] = estimated_bid
    return action


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _confidence(value: float, *, high: float, medium: float) -> str:
    if value >= high:
        return "High"
    if value >= medium:
        return "Medium"
    return "Low"


def _urgency_rank(urgency: str) -> int:
    if urgency == "Now":
        return 3
    if urgency == "Before waivers":
        return 2
    return 1
