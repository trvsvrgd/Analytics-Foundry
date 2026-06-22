"""Admin API for Foundry UI: ingest, tables, transformations, and workbench control plane."""

import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from analytics_foundry import workbench
from analytics_foundry.adapters import get_adapter
from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.config import (
    admin_auth_enabled,
    get_admin_api_key,
    get_ambient_ollama_base_url,
    get_ambient_ollama_model,
    get_default_league_id,
)
from analytics_foundry.silver import injuries as silver_injuries
from analytics_foundry.silver import league as silver_league
from analytics_foundry.silver import players as silver_players
from analytics_foundry.silver import rosters as silver_rosters
from analytics_foundry.silver import projections as silver_projections
from analytics_foundry.silver import tuesday_analytics as silver_tuesday
from analytics_foundry.gold import injury as gold_injury
from analytics_foundry.gold import league as gold_league
from analytics_foundry.gold import players as gold_players
from analytics_foundry.gold import projections as gold_projections
from analytics_foundry.gold import tuesday_analytics as gold_tuesday
from analytics_foundry.silver import ai_daily_brief as silver_aidb
from analytics_foundry.gold import ai_daily_brief as gold_aidb
from analytics_foundry.sql_loader import list_sql_files, medallion_layers, read_sql

_ADMIN_AUTH_COOKIE = "foundry_admin_key"
_ADMIN_AUTH_HEADER = "X-Foundry-Admin-Key"
_STARTUP_CATCHUP_STATUS: Dict[str, Any] = {
    "status": "idle",
    "message": "Startup catch-up has not run in this process.",
    "started_at": None,
    "finished_at": None,
    "due_count": 0,
    "executed_count": 0,
    "executed_jobs": [],
    "error": None,
}


def require_admin_auth(request: Request) -> None:
    """Protect /admin routes only when FOUNDRY_ADMIN_API_KEY is configured."""
    expected = get_admin_api_key()
    if expected is None:
        return
    provided = (
        request.headers.get(_ADMIN_AUTH_HEADER)
        or request.query_params.get("admin_key")
        or request.cookies.get(_ADMIN_AUTH_COOKIE)
    )
    if provided != expected:
        raise HTTPException(
            status_code=401,
            detail="Admin authentication required",
            headers={"WWW-Authenticate": "ApiKey"},
        )


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin_auth)])

_DEFAULT_SAMPLE_LIMIT = 100


class IngestLeagueBody(BaseModel):
    league_id: str


class IngestLeaguesBody(BaseModel):
    """One or more league IDs (comma-separated string or list)."""
    league_ids: str | list[str]


class QualityRuleBody(BaseModel):
    table_id: str
    type: str
    name: Optional[str] = None
    column: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    severity: str = "error"
    enabled: bool = True


class QualityRunBody(BaseModel):
    table_id: str
    rule_ids: Optional[List[str]] = None


class JobBody(BaseModel):
    name: str
    kind: str
    target: Dict[str, Any] = Field(default_factory=dict)
    schedule: Dict[str, Any] = Field(default_factory=lambda: {"type": "manual"})
    retry_count: int = 0
    retry_delay_seconds: int = 60
    enabled: bool = True
    next_run_at: Optional[float] = None


class ModelBody(BaseModel):
    name: str
    source_table_id: str
    target_table_id: Optional[str] = None
    operations: List[Dict[str, Any]] = Field(default_factory=list)


class SourceBody(BaseModel):
    connector: str
    name: Optional[str] = None
    source_id: Optional[str] = None
    table_name: Optional[str] = None
    format: Optional[str] = None
    filename: Optional[str] = None
    content: Optional[str] = None
    path: Optional[str] = None
    url: Optional[str] = None
    records_path: Optional[str] = None


class AmbientEvaluateBody(BaseModel):
    table_id: str
    model: Optional[str] = None
    limit: int = 100


class AmbientMessageIngestBody(BaseModel):
    device_id: str = "android"
    threads: List[Dict[str, Any]] = Field(default_factory=list)


class AmbientReviewApproveBody(BaseModel):
    updates: Dict[str, Any] = Field(default_factory=dict)
    reviewer_note: Optional[str] = None


class AmbientReviewIgnoreBody(BaseModel):
    reviewer_note: Optional[str] = None


class StorageRetentionBody(BaseModel):
    scopes: List[str] = Field(default_factory=lambda: ["bronze", "models", "run_history"])
    older_than_days: Optional[float] = 30
    older_than_seconds: Optional[float] = None
    table_id: Optional[str] = None
    now: Optional[float] = None
    confirm: bool = False


class AlertDeliveryTargetBody(BaseModel):
    name: Optional[str] = None
    kind: str = "webhook"
    url: str
    headers: Dict[str, Any] = Field(default_factory=dict)
    severities: List[str] = Field(default_factory=lambda: ["warning", "error"])
    enabled: bool = True
    timeout_seconds: int = 10


class AlertDeliveryToggleBody(BaseModel):
    enabled: bool


class WorkbenchImportBody(BaseModel):
    bundle: Dict[str, Any]
    mode: str = "merge"


def _body_dict(body: BaseModel) -> Dict[str, Any]:
    """Return model data on both Pydantic v1 and v2."""
    if hasattr(body, "model_dump"):
        return body.model_dump()
    return body.dict()


def startup_catchup_status() -> Dict[str, Any]:
    """Return the latest startup catch-up state for the current API process."""
    return dict(_STARTUP_CATCHUP_STATUS)


def _set_startup_catchup_status(**updates: Any) -> Dict[str, Any]:
    _STARTUP_CATCHUP_STATUS.update(updates)
    return startup_catchup_status()


@router.get("/config")
def admin_config() -> Dict[str, Any]:
    """Return config values for the admin UI (e.g. default league ID)."""
    return {
        "default_league_id": get_default_league_id(),
        "admin_auth_enabled": admin_auth_enabled(),
    }


@router.post("/ingest/league")
def admin_ingest_league(body: IngestLeagueBody) -> Dict[str, Any]:
    """Trigger league-scoped ingest for the given league_id. Uses ensure_league_ingested."""
    gold_league.ensure_league_ingested(body.league_id)
    workbench.record_run(
        "league",
        league_id=body.league_id,
        target={"league_id": body.league_id},
    )
    return {"ok": True, "league_id": body.league_id}


@router.get("/sources/templates")
def admin_source_templates() -> List[Dict[str, Any]]:
    """Return supported low-code source connectors."""
    return workbench.source_connector_templates()


@router.get("/sources")
def admin_sources() -> List[Dict[str, Any]]:
    """Return saved source definitions."""
    return workbench.list_sources()


@router.post("/sources/preview")
def admin_preview_source(body: SourceBody) -> Dict[str, Any]:
    """Preview a low-code source without writing bronze data."""
    try:
        return workbench.preview_source(_body_dict(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON source: {exc}")


@router.post("/sources/ingest")
def admin_ingest_source(body: SourceBody) -> Dict[str, Any]:
    """Ingest a low-code source into bronze storage."""
    try:
        return workbench.ingest_source(_body_dict(body))
    except ValueError as exc:
        run = workbench.record_run(
            "source_ingest",
            status="failed",
            target={"source_id": body.source_id, "table_name": body.table_name},
            message=str(exc),
        )
        workbench.create_alert(
            title="Source ingest failed",
            message=str(exc),
            severity="error",
            run_id=run["id"],
        )
        raise HTTPException(status_code=400, detail=str(exc))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON source: {exc}")


@router.get("/ambient/ollama/models")
def admin_ambient_ollama_models() -> Dict[str, Any]:
    """Return local Ollama model choices for ambient evaluation."""
    try:
        models = _ambient_list_ollama_models()
    except RuntimeError as exc:
        return {
            "available": False,
            "models": [],
            "selected_model": get_ambient_ollama_model(),
            "base_url": get_ambient_ollama_base_url(),
            "message": str(exc),
        }
    return {
        "available": True,
        "models": models,
        "selected_model": get_ambient_ollama_model(),
        "base_url": get_ambient_ollama_base_url(),
    }


@router.post("/ambient/messages/ingest")
def admin_ingest_ambient_messages(body: AmbientMessageIngestBody) -> Dict[str, Any]:
    """Receive selected Android message threads and write them to bronze."""
    adapter = get_adapter("android_messages")
    if adapter is None:
        raise HTTPException(status_code=503, detail="android_messages adapter not registered")
    before = len(bronze_store.get_raw("android_messages", "threads"))
    adapter.ingest_to_bronze(device_id=body.device_id, threads=body.threads)
    after = len(bronze_store.get_raw("android_messages", "threads"))
    row_count = max(0, after - before)
    table_id = workbench.table_id("bronze", "threads", source_id="android_messages")
    run = workbench.record_run(
        "adapter_ingest",
        target={"source_id": "android_messages", "table_id": table_id},
        details={"row_count": row_count, "device_id": body.device_id},
    )
    return {"ok": True, "table_id": table_id, "row_count": row_count, "run": run}


@router.post("/ambient/evaluate")
def admin_evaluate_ambient(body: AmbientEvaluateBody) -> Dict[str, Any]:
    """Evaluate a bronze table through the ambient confidence engine."""
    try:
        result = _run_ambient_evaluation(body.table_id, body.model, body.limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    run = workbench.record_run(
        "ambient_evaluate",
        status="succeeded",
        target={"table_id": body.table_id, "model": body.model},
        details=dict(result),
    )
    result["run"] = run
    return result


@router.get("/ambient/review")
def admin_ambient_review(status: Optional[str] = "open") -> List[Dict[str, Any]]:
    """Return ambient candidates awaiting or carrying human review decisions."""
    return workbench.get_silver_ambient_candidates(status=status)


@router.post("/ambient/review/{candidate_id}/approve")
def admin_approve_ambient_candidate(candidate_id: str, body: AmbientReviewApproveBody) -> Dict[str, Any]:
    """Approve a medium-confidence candidate into gold, with optional edits."""
    try:
        action = workbench.promote_ambient_candidate(
            candidate_id,
            updates=body.updates,
            reviewer_note=body.reviewer_note,
            status="approved",
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Ambient candidate not found: {candidate_id}")
    return {"ok": True, "action": action}


@router.post("/ambient/review/{candidate_id}/ignore")
def admin_ignore_ambient_candidate(candidate_id: str, body: AmbientReviewIgnoreBody) -> Dict[str, Any]:
    """Ignore a medium-confidence candidate so it never reaches gold."""
    try:
        candidate = workbench.ignore_ambient_candidate(candidate_id, body.reviewer_note)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Ambient candidate not found: {candidate_id}")
    return {"ok": True, "candidate": candidate}


def _ambient_list_ollama_models() -> List[str]:
    try:
        from ambient_context_engine import EvaluationUnavailable, list_ollama_models
    except ImportError as exc:
        raise RuntimeError("ambient-context-engine is not installed") from exc
    try:
        return list_ollama_models(get_ambient_ollama_base_url())
    except EvaluationUnavailable as exc:
        raise RuntimeError(str(exc)) from exc


def _ambient_evaluate_records(rows: List[Dict[str, Any]], model: str | None):
    try:
        from ambient_context_engine import evaluate_records
    except ImportError as exc:
        raise RuntimeError("ambient-context-engine is not installed") from exc
    return evaluate_records(rows, model=model)


def _ambient_route_candidates(candidates: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    try:
        from ambient_context_engine import route_candidates
    except ImportError as exc:
        raise RuntimeError("ambient-context-engine is not installed") from exc
    return route_candidates(candidates)


def _run_ambient_evaluation(table_id: str, model: str | None, limit: int = 100) -> Dict[str, Any]:
    rows = _rows_for_table_id(table_id)[: max(1, int(limit or 100))]
    selected_model = model or get_ambient_ollama_model()
    try:
        evaluation = _ambient_evaluate_records(rows, selected_model)
    except RuntimeError as exc:
        alert = workbench.create_alert(
            title="Ambient evaluation queued for review",
            message=str(exc),
            severity="warning",
            table_id=table_id,
        )
        return {
            "status": "succeeded",
            "evaluation_status": "queued_for_review",
            "table_id": table_id,
            "model": selected_model,
            "input_count": len(rows),
            "error": str(exc),
            "alert_id": alert["id"],
        }
    except Exception as exc:
        if exc.__class__.__name__ == "EvaluationUnavailable":
            alert = workbench.create_alert(
                title="Ambient evaluation queued for review",
                message=str(exc),
                severity="warning",
                table_id=table_id,
            )
            return {
                "status": "succeeded",
                "evaluation_status": "queued_for_review",
                "table_id": table_id,
                "model": selected_model,
                "input_count": len(rows),
                "error": str(exc),
                "alert_id": alert["id"],
            }
        raise

    candidates = [dict(candidate) for candidate in getattr(evaluation, "candidates", [])]
    routed = _ambient_route_candidates(candidates)
    stored = workbench.persist_ambient_candidates(
        routed["promote"] + routed["review"],
        source_table_id=table_id,
        model=getattr(evaluation, "model", None) or selected_model,
    )
    promoted = []
    review = []
    for candidate in stored:
        if candidate.get("route") == "promote":
            promoted.append(workbench.promote_ambient_candidate(candidate["id"], status="auto_promoted"))
        elif candidate.get("route") == "review":
            alert = workbench.create_alert(
                title=f"Ambient review needed: {candidate.get('title')}",
                message=str(candidate.get("confidence_reason") or "Medium-confidence ambient candidate needs review."),
                severity="warning",
                table_id=workbench.table_id("silver", workbench.AMBIENT_SILVER_TABLE),
            )
            review.append(workbench.attach_ambient_alert(candidate["id"], alert["id"]))
    return {
        "status": "succeeded",
        "evaluation_status": "evaluated",
        "table_id": table_id,
        "model": getattr(evaluation, "model", None) or selected_model,
        "input_count": len(rows),
        "candidate_count": len(candidates),
        "high_count": len(routed["promote"]),
        "medium_count": len(routed["review"]),
        "low_count": len(routed["ignore"]),
        "silver_count": len(stored),
        "gold_count": len(promoted),
        "review_count": len(review),
        "silver_table_id": workbench.table_id("silver", workbench.AMBIENT_SILVER_TABLE),
        "gold_table_id": workbench.table_id("gold", workbench.AMBIENT_GOLD_TABLE),
    }


def _parse_league_ids(raw: str | list[str]) -> list[str]:
    """Parse league_ids from string (comma/newline separated) or list."""
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    ids = []
    for part in raw.replace("\n", ",").split(","):
        pid = part.strip()
        if pid:
            ids.append(pid)
    return ids


def _rows_for_table_id(stable_table_id: str) -> List[Dict[str, Any]]:
    """Resolve a workbench table id to current rows."""
    try:
        parsed = workbench.parse_table_id(stable_table_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    layer = parsed["layer"]
    name = parsed["name"]
    if layer == "bronze":
        return bronze_store.get_raw(parsed["source_id"], name)
    if layer == "silver":
        if name == workbench.AMBIENT_SILVER_TABLE:
            return workbench.get_silver_ambient_candidates()
        if name == "players":
            return silver_players.get_players()
        if name == "league":
            return silver_league.get_leagues()
        if name == "rosters":
            return silver_rosters.get_rosters()
        if name == "injuries":
            return silver_injuries.get_injuries()
        if name == "weekly_matchups":
            return silver_projections.get_weekly_matchups()
        if name == "team_stats":
            return silver_projections.get_team_stats()
        if name == "player_weekly_stats":
            return silver_tuesday.get_player_weekly_stats()
        if name == "depth_charts":
            return silver_tuesday.get_depth_charts()
        if name == "vegas_weather":
            return silver_tuesday.get_vegas_weather()
        if name == "faab_history":
            return silver_tuesday.get_faab_history()
        if name == "ai_daily_brief_cleaned":
            return silver_aidb.get_cleaned_transcripts()
        raise HTTPException(status_code=404, detail=f"Unknown silver table: {name}")
    if layer == "gold":
        if name == workbench.AMBIENT_GOLD_TABLE:
            return workbench.get_gold_ambient_actions()
        if name == "available_players":
            return gold_players.get_available_players()
        if name == "injury":
            return gold_injury.get_injury_report()
        if name == "defense_projections":
            return gold_projections.get_defense_projections(get_default_league_id())
        if name == "win_probability":
            return gold_projections.get_win_probability(get_default_league_id())
        if name == "tuesday_waiver_targets":
            return gold_tuesday.get_waiver_targets(get_default_league_id())
        if name == "tuesday_trade_regression":
            return gold_tuesday.get_trade_regression(get_default_league_id())
        if name == "tuesday_injury_cascade":
            return gold_tuesday.get_injury_cascade(get_default_league_id())
        if name == "tuesday_roster_utility":
            return gold_tuesday.get_roster_utility(get_default_league_id())
        if name == "tuesday_waiver_bids":
            return gold_tuesday.get_waiver_bids(get_default_league_id())
        if name == "mba_coursework_impact":
            return gold_aidb.get_mba_impact()
        if name == "ai_platform_product_strategy":
            return gold_aidb.get_product_strategy_impact()
        raise HTTPException(status_code=404, detail=f"Unknown gold table: {name}")
    if layer == "model":
        model = workbench.get_model(name)
        if model is None:
            raise HTTPException(status_code=404, detail=f"Unknown model table: {name}")
        if workbench.model_has_materialized_rows(model["id"]):
            return workbench.get_materialized_model_rows(model["id"])
        return workbench.preview_model(model["id"], _rows_for_table_id, limit=1000)["rows"]
    raise HTTPException(status_code=400, detail=f"Unknown layer: {layer}")


def _storage_path_for_table_id(stable_table_id: str) -> str | None:
    parsed = workbench.parse_table_id(stable_table_id)
    if parsed["layer"] == "bronze":
        return workbench.bronze_storage_path(parsed["source_id"], parsed["name"])
    if parsed["layer"] == "model":
        model = workbench.get_model(parsed["name"])
        if model is None or not workbench.model_has_materialized_rows(model["id"]):
            return None
        return workbench.model_storage_path(model["id"])
    if parsed["layer"] == "silver" and parsed["name"] == workbench.AMBIENT_SILVER_TABLE:
        return workbench.ambient_storage_path("silver", workbench.AMBIENT_SILVER_TABLE)
    if parsed["layer"] == "gold" and parsed["name"] == workbench.AMBIENT_GOLD_TABLE:
        return workbench.ambient_storage_path("gold", workbench.AMBIENT_GOLD_TABLE)
    return None


def _profile_for_table_id(stable_table_id: str) -> Dict[str, Any]:
    rows = _rows_for_table_id(stable_table_id)
    return workbench.table_profile(
        stable_table_id,
        rows,
        storage_path=_storage_path_for_table_id(stable_table_id),
    )


@router.post("/ingest/leagues")
def admin_ingest_leagues(body: IngestLeaguesBody) -> Dict[str, Any]:
    """Trigger league-scoped ingest for one or more league IDs."""
    ids = _parse_league_ids(body.league_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="At least one league_id required")
    for lid in ids:
        gold_league.ensure_league_ingested(lid)
        workbench.record_run("league", league_id=lid, target={"league_id": lid})
    return {"ok": True, "league_ids": ids}


@router.post("/ingest/broad")
def admin_ingest_broad() -> Dict[str, Any]:
    """Trigger broad NFL ingest (no league_id). Calls adapter ingest_to_bronze()."""
    adapter = get_adapter("nfl_sleeper")
    if adapter is None:
        raise HTTPException(status_code=503, detail="nfl_sleeper adapter not registered")
    adapter.ingest_to_bronze()
    workbench.record_run("broad", target={"source_id": "nfl_sleeper"})
    return {"ok": True}


@router.get("/tables")
def admin_list_tables() -> Dict[str, Any]:
    """List medallion datasets with schema, freshness, storage, and lineage metadata."""
    bronze = []
    for source_id, table, row_count in bronze_store.list_tables():
        stable_id = workbench.table_id("bronze", table, source_id=source_id)
        profile = _profile_for_table_id(stable_id)
        profile["table"] = table
        profile["row_count"] = row_count
        bronze.append(profile)

    silver = [
        _profile_for_table_id(workbench.table_id("silver", name))
        for name in ("players", "league", "rosters", "injuries", "weekly_matchups", "team_stats", "player_weekly_stats", "depth_charts", "vegas_weather", "faab_history", workbench.AMBIENT_SILVER_TABLE, "ai_daily_brief_cleaned")
    ]
    gold = [
        _profile_for_table_id(workbench.table_id("gold", name))
        for name in ("available_players", "injury", "defense_projections", "win_probability", "tuesday_waiver_targets", "tuesday_trade_regression", "tuesday_injury_cascade", "tuesday_roster_utility", "tuesday_waiver_bids", workbench.AMBIENT_GOLD_TABLE, "mba_coursework_impact", "ai_platform_product_strategy")
    ]
    models = [
        _profile_for_table_id(model["target_table_id"])
        for model in workbench.list_models()
        if model.get("target_table_id", "").startswith("model:")
    ]
    return {"bronze": bronze, "silver": silver, "gold": gold, "models": models}


@router.get("/tables/{layer}/{source_or_name}")
def admin_sample_table_two_segments(
    layer: str, source_or_name: str, table: Optional[str] = None
) -> Dict[str, Any]:
    """Sample table: bronze requires table (source_or_name=source_id); gold/silver use source_or_name as name."""
    limit = _DEFAULT_SAMPLE_LIMIT
    if layer == "bronze":
        if table is None:
            raise HTTPException(
                status_code=400,
                detail="Bronze sample requires path: /admin/tables/bronze/{source_id}/{table}",
            )
        rows = bronze_store.get_raw(source_or_name, table)[:limit]
        return {"layer": layer, "source_id": source_or_name, "table": table, "rows": rows, "limit": limit}
    if layer == "silver":
        if source_or_name == workbench.AMBIENT_SILVER_TABLE:
            rows = workbench.get_silver_ambient_candidates()[:limit]
            return {"layer": "silver", "table": source_or_name, "rows": rows, "limit": limit}
        if source_or_name == "players":
            rows = silver_players.get_players()[:limit]
        elif source_or_name == "league":
            rows = silver_league.get_leagues()[:limit]
        elif source_or_name == "rosters":
            rows = silver_rosters.get_rosters()[:limit]
        elif source_or_name == "injuries":
            rows = silver_injuries.get_injuries()[:limit]
        elif source_or_name == "ai_daily_brief_cleaned":
            rows = silver_aidb.get_cleaned_transcripts()[:limit]
        else:
            raise HTTPException(status_code=404, detail=f"Unknown silver table: {source_or_name}")
        return {"layer": layer, "name": source_or_name, "rows": rows, "limit": limit}
    if layer == "gold":
        if source_or_name == workbench.AMBIENT_GOLD_TABLE:
            rows = workbench.get_gold_ambient_actions()[:limit]
            return {"layer": "gold", "table": source_or_name, "rows": rows, "limit": limit}
        if source_or_name == "available_players":
            rows = gold_players.get_available_players()[:limit]
        elif source_or_name == "injury":
            rows = gold_injury.get_injury_report()[:limit]
        elif source_or_name == "mba_coursework_impact":
            rows = gold_aidb.get_mba_impact()[:limit]
        elif source_or_name == "ai_platform_product_strategy":
            rows = gold_aidb.get_product_strategy_impact()[:limit]
        else:
            raise HTTPException(status_code=404, detail=f"Unknown gold table: {source_or_name}")
        return {"layer": layer, "name": source_or_name, "rows": rows, "limit": limit}
    if layer == "model":
        rows = _rows_for_table_id(workbench.table_id("model", source_or_name))[:limit]
        return {"layer": layer, "name": source_or_name, "rows": rows, "limit": limit}
    raise HTTPException(status_code=400, detail=f"Unknown layer: {layer}")


@router.get("/tables/{layer}/{source_or_name}/{table}")
def admin_sample_bronze(
    layer: str, source_or_name: str, table: str
) -> Dict[str, Any]:
    """Sample bronze table: GET /admin/tables/bronze/{source_id}/{table}."""
    if layer != "bronze":
        raise HTTPException(status_code=400, detail="Three-segment path is for bronze only")
    limit = _DEFAULT_SAMPLE_LIMIT
    rows = bronze_store.get_raw(source_or_name, table)[:limit]
    return {"layer": "bronze", "source_id": source_or_name, "table": table, "rows": rows, "limit": limit}


@router.get("/transformations")
def admin_list_transformations() -> Dict[str, Any]:
    """List SQL transformation files by layer (from sql_loader)."""
    out = {}
    for layer in medallion_layers():
        files = list_sql_files(layer)
        out[layer] = [f.replace(".sql", "") for f in files]
    return out


@router.get("/transformations/{layer}/{name}")
def admin_get_transformation(layer: str, name: str) -> Dict[str, Any]:
    """Return SQL content for sql/<layer>/<name>.sql."""
    if layer not in medallion_layers():
        raise HTTPException(status_code=400, detail=f"Unknown layer: {layer}")
    try:
        content = read_sql(layer, name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Transformation not found: {layer}/{name}")
    return {"layer": layer, "name": name, "sql": content}


@router.get("/runs")
def admin_list_runs() -> List[Dict[str, Any]]:
    """Return persisted run history."""
    return workbench.list_runs()


@router.get("/league/validate")
def admin_validate_league(league_id: str) -> Dict[str, Any]:
    """Validate league ID (same as POST /league/validate). For UI convenience."""
    return gold_league.validate_league(league_id)


@router.get("/table-profiles/{stable_table_id:path}")
def admin_table_profile(stable_table_id: str) -> Dict[str, Any]:
    """Return schema, freshness, storage, and lineage for one table id."""
    return _profile_for_table_id(stable_table_id)


@router.get("/lineage")
def admin_lineage() -> Dict[str, Any]:
    """Return deterministic lineage edges for core and low-code model assets."""
    return {"edges": workbench.list_lineage_edges()}


@router.get("/lineage/{stable_table_id:path}")
def admin_lineage_for_table(stable_table_id: str) -> Dict[str, Any]:
    """Return direct upstream and downstream lineage for one table id."""
    return {
        "table_id": stable_table_id,
        **workbench.lineage_for_table(stable_table_id),
    }


@router.get("/quality/authoring-context/{stable_table_id:path}")
def admin_quality_authoring_context(stable_table_id: str) -> Dict[str, Any]:
    """Return schema-aware quality rule authoring metadata for one table."""
    return workbench.quality_authoring_context(
        stable_table_id,
        _rows_for_table_id(stable_table_id),
        reference_tables=_quality_reference_tables(),
    )


def _quality_reference_tables() -> List[Dict[str, Any]]:
    table_groups = admin_list_tables()
    references = []
    for layer in ("bronze", "silver", "gold", "models"):
        for table in table_groups.get(layer, []):
            references.append(
                {
                    "table_id": table["table_id"],
                    "label": table["table_id"],
                    "columns": [column["name"] for column in table.get("schema") or []],
                }
            )
    return references


@router.get("/quality/templates")
def admin_quality_templates() -> List[Dict[str, Any]]:
    """Return supported data quality rule templates."""
    return workbench.quality_templates()


@router.get("/quality/rules")
def admin_quality_rules(table_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return saved quality rules, optionally filtered to one table."""
    return workbench.list_quality_rules(table_id)


@router.post("/quality/rules")
def admin_create_quality_rule(body: QualityRuleBody) -> Dict[str, Any]:
    """Create a data quality rule attached to a table."""
    try:
        return workbench.create_quality_rule(_body_dict(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/quality/run")
def admin_run_quality(body: QualityRunBody) -> Dict[str, Any]:
    """Run enabled quality rules for one table and record alerts for failures."""
    start = time.time()
    try:
        results = workbench.run_quality_rules(body.table_id, _rows_for_table_id, body.rule_ids)
    except HTTPException:
        raise
    except Exception as exc:
        run = workbench.record_run(
            "quality_check",
            status="failed",
            target={"table_id": body.table_id},
            message=str(exc),
            started_at=start,
        )
        workbench.create_alert(
            title="Quality check failed",
            message=str(exc),
            severity="error",
            table_id=body.table_id,
            run_id=run["id"],
        )
        raise HTTPException(status_code=400, detail=str(exc))
    status = "failed" if any(r["status"] in {"failed", "error"} for r in results) else "succeeded"
    run = workbench.record_run(
        "quality_check",
        status=status,
        target={"table_id": body.table_id},
        details={"result_count": len(results)},
        started_at=start,
    )
    return {"run": run, "results": results}


@router.get("/quality/results")
def admin_quality_results(table_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return latest quality check results."""
    return workbench.list_quality_results(table_id)


@router.get("/alerts")
def admin_alerts(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return in-app alerts from failed jobs and quality checks."""
    return workbench.list_alerts(status)


@router.get("/alerts/delivery/templates")
def admin_alert_delivery_templates() -> List[Dict[str, Any]]:
    """Return supported external alert delivery adapters."""
    return workbench.alert_delivery_templates()


@router.get("/alerts/delivery-targets")
def admin_alert_delivery_targets() -> List[Dict[str, Any]]:
    """Return saved external alert delivery targets."""
    return workbench.list_alert_delivery_targets()


@router.post("/alerts/delivery-targets")
def admin_create_alert_delivery_target(body: AlertDeliveryTargetBody) -> Dict[str, Any]:
    """Create a webhook-style alert delivery target."""
    try:
        return workbench.create_alert_delivery_target(_body_dict(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/alerts/delivery-targets/{target_id}/toggle")
def admin_toggle_alert_delivery_target(target_id: str, body: AlertDeliveryToggleBody) -> Dict[str, Any]:
    """Enable or disable one alert delivery target."""
    target = workbench.set_alert_delivery_target_enabled(target_id, body.enabled)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Alert delivery target not found: {target_id}")
    return target


@router.post("/alerts/delivery-targets/{target_id}/test")
def admin_test_alert_delivery_target(target_id: str) -> Dict[str, Any]:
    """Send a synthetic test alert through one delivery target."""
    delivery = workbench.test_alert_delivery_target(target_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail=f"Alert delivery target not found: {target_id}")
    return delivery


@router.get("/alerts/deliveries")
def admin_alert_deliveries(
    alert_id: Optional[str] = None,
    target_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Return external alert delivery attempts."""
    return workbench.list_alert_deliveries(alert_id=alert_id, target_id=target_id, limit=limit)


@router.post("/alerts/{alert_id}/ack")
def admin_ack_alert(alert_id: str) -> Dict[str, Any]:
    """Acknowledge an in-app alert."""
    alert = workbench.acknowledge_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert not found: {alert_id}")
    return alert


@router.get("/jobs")
def admin_jobs() -> List[Dict[str, Any]]:
    """Return saved job definitions."""
    return workbench.list_jobs()


@router.get("/jobs/defaults")
def admin_default_jobs() -> Dict[str, Any]:
    """Return the built-in default ingest job templates."""
    return {"jobs": workbench.default_ingest_job_templates()}


@router.post("/jobs")
def admin_create_job(body: JobBody) -> Dict[str, Any]:
    """Create a persisted job definition."""
    try:
        return workbench.create_job(_body_dict(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/jobs/{job_id}/run")
def admin_run_job(job_id: str) -> Dict[str, Any]:
    """Run a saved job immediately."""
    job = workbench.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return _run_job(job, trigger="manual", raise_on_failure=True)


def _run_job(
    job: Dict[str, Any],
    trigger: str,
    raise_on_failure: bool,
    execution_time: Optional[float] = None,
) -> Dict[str, Any]:
    start = time.time() if execution_time is None else float(execution_time)
    try:
        details = _execute_job(job)
        status = details.pop("status", "succeeded")
        details["trigger"] = trigger
        run = workbench.record_run(
            job["kind"],
            status=status,
            league_id=details.get("league_id"),
            job_id=job["id"],
            target=job.get("target") or {},
            details=details,
            started_at=start,
            finished_at=execution_time,
        )
    except HTTPException as exc:
        details = {"trigger": trigger}
        run = workbench.record_run(
            job["kind"],
            status="failed",
            job_id=job["id"],
            target=job.get("target") or {},
            message=str(exc.detail),
            details=details,
            started_at=start,
            finished_at=execution_time,
        )
        workbench.create_alert(
            title=f"Job failed: {job['name']}",
            message=str(exc.detail),
            severity="error",
            run_id=run["id"],
        )
        workbench.mark_job_run(job["id"], run)
        if raise_on_failure:
            raise
        return {"job": workbench.get_job(job["id"]), "run": run, "details": details, "error": str(exc.detail)}
    workbench.mark_job_run(job["id"], run)
    return {"job": workbench.get_job(job["id"]), "run": run, "details": details}


@router.get("/scheduler/status")
def admin_scheduler_status(now: Optional[float] = None) -> Dict[str, Any]:
    """Return due-job status for the local scheduler."""
    return workbench.scheduler_status(now)


@router.post("/scheduler/run-due")
def admin_scheduler_run_due(limit: int = 20, now: Optional[float] = None) -> Dict[str, Any]:
    """Run enabled jobs whose next_run_at is due."""
    return run_due_jobs_once(limit=limit, now=now, trigger="scheduler")


@router.get("/scheduler/startup-catchup")
def admin_scheduler_startup_catchup() -> Dict[str, Any]:
    """Return startup catch-up status for missed scheduled jobs."""
    return startup_catchup_status()


def run_startup_catchup_once(
    limit: int = 20,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Run jobs that were already due when the API process started."""
    current = time.time() if now is None else float(now)
    due_jobs = workbench.list_due_jobs(current)
    due_summaries = [_job_summary(job) for job in due_jobs]
    _set_startup_catchup_status(
        status="running",
        message=(
            f"Startup catch-up is running {len(due_jobs)} overdue job(s)."
            if due_jobs
            else "Startup catch-up checked; no overdue jobs."
        ),
        started_at=current,
        finished_at=None,
        due_count=len(due_jobs),
        executed_count=0,
        due_jobs=due_summaries,
        executed_jobs=[],
        error=None,
    )
    if not due_jobs:
        return _set_startup_catchup_status(
            status="completed",
            message="Startup catch-up checked; no overdue jobs.",
            finished_at=current,
        )

    try:
        result = run_due_jobs_once(limit=limit, now=current, trigger="startup_catchup")
    except Exception as exc:
        workbench.create_alert(
            title="Startup catch-up failed",
            message=str(exc),
            severity="error",
        )
        return _set_startup_catchup_status(
            status="failed",
            message=f"Startup catch-up failed: {exc}",
            finished_at=time.time(),
            error=str(exc),
        )

    executed_jobs = [
        _job_summary(item.get("job") or {})
        for item in result.get("executed") or []
    ]
    failed = [
        item
        for item in result.get("executed") or []
        if ((item.get("run") or {}).get("status") not in {None, "succeeded"})
    ]
    status = "completed_with_errors" if failed else "completed"
    message = f"Startup catch-up ran {result.get('executed_count') or 0} overdue job(s)."
    if failed:
        message += f" {len(failed)} job(s) failed; check Alerts for details."
    if result.get("executed_count"):
        names = ", ".join(job.get("name") or job.get("id") or "job" for job in executed_jobs)
        workbench.create_alert(
            title="Startup catch-up ran overdue jobs",
            message=f"{message} Jobs: {names}",
            severity="info",
        )
    return _set_startup_catchup_status(
        status=status,
        message=message,
        finished_at=time.time(),
        due_count=result.get("due_count") or 0,
        executed_count=result.get("executed_count") or 0,
        remaining_due_count=result.get("remaining_due_count") or 0,
        executed_jobs=executed_jobs,
        result=result,
        error=None,
    )


def _job_summary(job: Dict[str, Any]) -> Dict[str, Any]:
    target = job.get("target") or {}
    return {
        "id": job.get("id"),
        "name": job.get("name"),
        "kind": job.get("kind"),
        "source_id": target.get("source_id"),
        "next_run_at": job.get("next_run_at"),
        "last_status": job.get("last_status"),
    }


def run_due_jobs_once(
    limit: int = 20,
    now: Optional[float] = None,
    trigger: str = "scheduler",
) -> Dict[str, Any]:
    current = time.time() if now is None else float(now)
    due_jobs = workbench.list_due_jobs(current)
    executed = []
    for job in due_jobs[: max(0, limit)]:
        executed.append(
            _run_job(
                job,
                trigger=trigger,
                raise_on_failure=False,
                execution_time=current,
            )
        )
    return {
        "now": current,
        "due_count": len(due_jobs),
        "executed_count": len(executed),
        "remaining_due_count": max(0, len(due_jobs) - len(executed)),
        "executed": executed,
        "status": workbench.scheduler_status(current),
    }


def _execute_job(job: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(job.get("kind") or "")
    target = job.get("target") or {}
    if kind in {"broad", "broad_ingest"}:
        adapter = get_adapter("nfl_sleeper")
        if adapter is None:
            raise HTTPException(status_code=503, detail="nfl_sleeper adapter not registered")
        adapter.ingest_to_bronze()
        return {"status": "succeeded", "source_id": "nfl_sleeper"}
    if kind in {"league", "league_ingest"}:
        league_id = str(target.get("league_id") or "")
        if not league_id:
            raise HTTPException(status_code=400, detail="league_id target is required")
        gold_league.ensure_league_ingested(league_id)
        return {"status": "succeeded", "league_id": league_id}
    if kind == "quality_check":
        table_id = str(target.get("table_id") or "")
        if not table_id:
            raise HTTPException(status_code=400, detail="table_id target is required")
        results = workbench.run_quality_rules(table_id, _rows_for_table_id)
        status = "failed" if any(r["status"] in {"failed", "error"} for r in results) else "succeeded"
        return {"status": status, "table_id": table_id, "result_count": len(results)}
    if kind == "model_preview":
        model_id = str(target.get("model_id") or "")
        if not model_id:
            raise HTTPException(status_code=400, detail="model_id target is required")
        preview = workbench.preview_model(model_id, _rows_for_table_id, limit=20)
        return {"status": "succeeded", "model_id": model_id, "row_count": preview["row_count"]}
    if kind == "model_materialize":
        model_id = str(target.get("model_id") or "")
        if not model_id:
            raise HTTPException(status_code=400, detail="model_id target is required")
        try:
            result = workbench.materialize_model(
                model_id,
                _rows_for_table_id,
                record_run_history=False,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Model not found: {model_id}")
        return {
            "status": "succeeded",
            "model_id": model_id,
            "table_id": result["table_id"],
            "row_count": result["row_count"],
        }
    if kind == "source_ingest":
        source_id = str(target.get("source_id") or "")
        if not source_id:
            raise HTTPException(status_code=400, detail="source_id target is required")
        try:
            result = workbench.ingest_source_by_id(source_id, record_run_history=False)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {
            "status": "succeeded",
            "source_id": source_id,
            "table_id": result["table_id"],
            "row_count": result["row_count"],
        }
    if kind == "adapter_ingest":
        source_id = str(target.get("source_id") or "")
        if not source_id:
            raise HTTPException(status_code=400, detail="source_id target is required")
        adapter = get_adapter(source_id)
        if adapter is None:
            raise HTTPException(status_code=404, detail=f"Adapter not found: {source_id}")
        params = target.get("params") or {}
        if not isinstance(params, dict):
            raise HTTPException(status_code=400, detail="adapter_ingest params must be an object")
        before = {
            (src, table): count
            for src, table, count in bronze_store.list_tables()
            if src == source_id
        }
        adapter.ingest_to_bronze(**params)
        after = {
            (src, table): count
            for src, table, count in bronze_store.list_tables()
            if src == source_id
        }
        row_count = sum(max(0, count - before.get(key, 0)) for key, count in after.items())
        return {
            "status": "succeeded",
            "source_id": source_id,
            "row_count": row_count,
            "tables": [
                workbench.table_id("bronze", table, source_id=src)
                for (src, table), count in after.items()
            ],
        }
    if kind == "ambient_evaluate":
        table_id = str(target.get("table_id") or "")
        if not table_id:
            raise HTTPException(status_code=400, detail="table_id target is required")
        try:
            return _run_ambient_evaluation(
                table_id,
                model=target.get("model"),
                limit=int(target.get("limit") or 100),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    raise HTTPException(status_code=400, detail=f"Unknown job kind: {kind}")


@router.get("/models/operations")
def admin_model_operations() -> List[Dict[str, Any]]:
    """Return supported low-code modeling operations."""
    return workbench.model_operation_templates()


@router.get("/models")
def admin_models() -> List[Dict[str, Any]]:
    """Return saved low-code model definitions."""
    return workbench.list_models()


@router.post("/models")
def admin_create_model(body: ModelBody) -> Dict[str, Any]:
    """Create a saved low-code model definition."""
    try:
        return workbench.create_model(_body_dict(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/models/{model_id}/preview")
def admin_preview_model(model_id: str) -> Dict[str, Any]:
    """Preview a low-code model by applying its JSON operations in-memory."""
    try:
        return workbench.preview_model(model_id, _rows_for_table_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Model not found: {model_id}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/models/{model_id}/materialize")
def admin_materialize_model(model_id: str) -> Dict[str, Any]:
    """Run a low-code model and overwrite its durable model table."""
    try:
        return workbench.materialize_model(model_id, _rows_for_table_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Model not found: {model_id}")
    except ValueError as exc:
        run = workbench.record_run(
            "model_materialize",
            status="failed",
            target={"model_id": model_id},
            message=str(exc),
        )
        workbench.create_alert(
            title="Model materialization failed",
            message=str(exc),
            severity="error",
            run_id=run["id"],
        )
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/storage")
def admin_storage() -> Dict[str, Any]:
    """Return local storage allocation details."""
    return workbench.data_root_info()


@router.get("/diagnostics")
def admin_diagnostics(now: Optional[float] = None) -> Dict[str, Any]:
    """Return runtime health and diagnostics for storage, metadata, adapters, and scheduler."""
    return workbench.runtime_diagnostics(now=now)


@router.post("/storage/retention/preview")
def admin_storage_retention_preview(body: StorageRetentionBody) -> Dict[str, Any]:
    """Preview files matched by a retention policy without deleting them."""
    try:
        return workbench.preview_storage_cleanup(_body_dict(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/storage/cleanup")
def admin_storage_cleanup(body: StorageRetentionBody) -> Dict[str, Any]:
    """Delete Foundry-owned files matched by a confirmed retention policy."""
    payload = _body_dict(body)
    if not payload.get("confirm"):
        raise HTTPException(status_code=400, detail="Cleanup requires confirm=true")
    try:
        return workbench.apply_storage_cleanup(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/export")
def admin_export_bundle(include_history: bool = False) -> Dict[str, Any]:
    """Export portable workbench metadata as a JSON bundle."""
    return workbench.export_bundle(include_history=include_history)


@router.post("/import")
def admin_import_bundle(body: WorkbenchImportBody) -> Dict[str, Any]:
    """Import a portable workbench metadata JSON bundle."""
    payload = _body_dict(body)
    try:
        return workbench.import_bundle(payload["bundle"], mode=payload.get("mode", "merge"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


_ADMIN_UI_ROOT = Path(__file__).resolve().parent / "admin_ui"


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def admin_ui_index(request: Request):
    """Serve admin UI at GET /admin and GET /admin/."""
    index = _ADMIN_UI_ROOT / "index.html"
    if not index.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Admin UI not found")
    response = FileResponse(index, media_type="text/html")
    expected = get_admin_api_key()
    provided = request.query_params.get("admin_key")
    if expected is not None and provided == expected:
        response.set_cookie(
            _ADMIN_AUTH_COOKIE,
            provided,
            httponly=True,
            samesite="lax",
        )
    return response
