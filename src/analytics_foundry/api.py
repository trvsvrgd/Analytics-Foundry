"""REST API for sleeper-stream-scribe: players/available, league/validate, injury. CORS enabled."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from analytics_foundry.adapters import register_adapter
from analytics_foundry.adapters.nfl_sleeper import NFLSleeperAdapter
from analytics_foundry.admin_routes import router as admin_router
from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.config import (
    audit_log_enabled,
    get_default_league_id,
    prometheus_enabled,
    validate_startup_config,
)
from analytics_foundry.exceptions import ConfigurationError
from analytics_foundry.gold import injury as gold_injury
from analytics_foundry.gold import league as gold_league
from analytics_foundry.gold import players as gold_players
from analytics_foundry.gold import recommendations as gold_recommendations
from analytics_foundry.health import get_liveness, get_readiness
from analytics_foundry.logging_config import setup_logging
from analytics_foundry.telemetry import incr_counter, prometheus_text

_LOG = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Register NFL/Sleeper adapter, validate config, load bronze, configure logging."""
    setup_logging()
    try:
        validate_startup_config()
    except ConfigurationError:
        _LOG.exception("startup configuration invalid")
        raise
    register_adapter(NFLSleeperAdapter)
    bronze_store.load_from_disk()
    _LOG.info("analytics_foundry startup complete (pid=%s)", os.getpid())
    yield
    _LOG.info("analytics_foundry shutdown")


app = FastAPI(title="Analytics Foundry API", lifespan=lifespan)
app.include_router(admin_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def foundry_request_middleware(request: Request, call_next):
    incr_counter("http_requests_total")
    if audit_log_enabled():
        _LOG.info("audit method=%s path=%s client=%s", request.method, request.url.path, request.client)
    return await call_next(request)


class LeagueValidateBody(BaseModel):
    league_id: str


@app.get("/health")
def health():
    """Liveness: process is serving requests."""
    return get_liveness()


@app.get("/ready")
def ready():
    """Readiness: core dependencies (adapter) available."""
    body = get_readiness()
    if not body.get("ready"):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content=body)
    return body


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Prometheus text metrics when FOUNDRY_PROMETHEUS=1."""
    if not prometheus_enabled():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Metrics disabled; set FOUNDRY_PROMETHEUS=1")
    return prometheus_text()


@app.get("/players/available")
def players_available(league_id: str | None = None):
    """Available (unrostered) players. Optional query: league_id. Uses default league if omitted."""
    lid = league_id or get_default_league_id()
    gold_league.ensure_league_ingested(lid)
    return gold_players.get_available_players(league_id=lid)


@app.post("/league/validate")
def league_validate(body: LeagueValidateBody):
    """Validate league ID. Response: valid, league_id, league_name."""
    return gold_league.validate_league(body.league_id)


@app.get("/injury")
def injury_report(league_id: str | None = None):
    """Injury report. Optional query: league_id. Uses default league if omitted."""
    lid = league_id or get_default_league_id()
    gold_league.ensure_league_ingested(lid)
    return gold_injury.get_injury_report(league_id=lid)


@app.get("/recommendations/waiver")
def recommendations_waiver(league_id: str | None = None, limit: int = 20):
    """Waiver recommendations: available players with score.

    Response shape: {recommendations, league_id}. Default league if league_id omitted.
    """
    lid = league_id or get_default_league_id()
    gold_league.ensure_league_ingested(lid)
    recs = gold_recommendations.get_waiver_recommendations(league_id=lid, limit=limit)
    return {"recommendations": recs, "league_id": lid}
