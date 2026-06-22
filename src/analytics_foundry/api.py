"""REST API for sleeper-stream-scribe: players/available, league/validate, injury. CORS enabled."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from analytics_foundry.adapters import register_adapter
from analytics_foundry.adapters.android_messages import AndroidMessagesAdapter
from analytics_foundry.adapters.gmail import GmailAdapter
from analytics_foundry.adapters.google_calendar import GoogleCalendarAdapter
from analytics_foundry.adapters.nfl_weekly_feed import NFLWeeklyFeedAdapter
from analytics_foundry.adapters.ai_daily_brief import AiDailyBriefAdapter
from analytics_foundry.adapters.nfl_sleeper import NFLSleeperAdapter
from analytics_foundry.admin_routes import router as admin_router, run_due_jobs_once, run_startup_catchup_once
from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.config import (
    audit_log_enabled,
    get_default_league_id,
    prometheus_enabled,
    scheduler_enabled,
    scheduler_interval_seconds,
    validate_startup_config,
)
from analytics_foundry.exceptions import ConfigurationError
from analytics_foundry.gold import injury as gold_injury
from analytics_foundry.gold import league as gold_league
from analytics_foundry.gold import manager_brief as gold_manager_brief
from analytics_foundry.gold import players as gold_players
from analytics_foundry.gold import recommendations as gold_recommendations
from analytics_foundry.health import get_liveness, get_readiness
from analytics_foundry.logging_config import setup_logging
from analytics_foundry.telemetry import incr_counter, prometheus_text

logger = logging.getLogger(__name__)
_LOG = logger


async def _startup_catchup() -> None:
    try:
        await asyncio.to_thread(run_startup_catchup_once, 20, None)
    except Exception:
        logger.exception("Startup catch-up failed")


async def _scheduler_loop(initial_delay: float = 0.0) -> None:
    interval = scheduler_interval_seconds()
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)
    while True:
        try:
            await asyncio.to_thread(run_due_jobs_once, 20, None, "scheduler_loop")
        except Exception:
            logger.exception("Local scheduler tick failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Register all adapters, validate configuration, load/bootstrap data, and run local job scheduler."""
    setup_logging()
    try:
        validate_startup_config()
    except ConfigurationError:
        logger.exception("Startup configuration invalid")
        raise

    register_adapter(NFLSleeperAdapter)
    register_adapter(GmailAdapter)
    register_adapter(GoogleCalendarAdapter)
    register_adapter(AndroidMessagesAdapter)
    register_adapter(NFLWeeklyFeedAdapter)
    register_adapter(AiDailyBriefAdapter)
    bronze_store.load_from_disk()

    workbench_result = None
    try:
        from analytics_foundry import workbench

        workbench_result = workbench.ensure_default_ingest_jobs()
        if workbench_result.get("created_count"):
            logger.info("Seeded %s default ingest job(s)", workbench_result["created_count"])
    except Exception:
        logger.exception("Default ingest job bootstrap failed")

    scheduler_task = None
    startup_catchup_task = None
    if scheduler_enabled():
        startup_catchup_task = asyncio.create_task(_startup_catchup())
        scheduler_task = asyncio.create_task(_scheduler_loop(initial_delay=scheduler_interval_seconds()))

    logger.info("analytics_foundry startup complete (pid=%s)", os.getpid())
    try:
        yield
    finally:
        logger.info("analytics_foundry shutting down")
        if startup_catchup_task is not None:
            startup_catchup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await startup_catchup_task
        if scheduler_task is not None:
            scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler_task
        logger.info("analytics_foundry shutdown complete")


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


@app.get("/recommendations/manager-brief")
def recommendations_manager_brief(league_id: str | None = None, limit: int = 12):
    """Fantasy manager insight bundle assembled from gold recommendation models."""
    lid = league_id or get_default_league_id()
    gold_league.ensure_league_ingested(lid)
    return gold_manager_brief.get_manager_brief(league_id=lid, limit=limit)
