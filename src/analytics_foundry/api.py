"""REST API for sleeper-stream-scribe: players/available, league/validate, injury. CORS enabled."""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analytics_foundry.admin_routes import router as admin_router, run_due_jobs_once, run_startup_catchup_once
from analytics_foundry.adapters import register_adapter
from analytics_foundry.adapters.android_messages import AndroidMessagesAdapter
from analytics_foundry.adapters.gmail import GmailAdapter
from analytics_foundry.adapters.google_calendar import GoogleCalendarAdapter
from analytics_foundry.adapters.nfl_weekly_feed import NFLWeeklyFeedAdapter
from analytics_foundry.adapters.ai_daily_brief import AiDailyBriefAdapter
from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.adapters.nfl_sleeper import NFLSleeperAdapter
from analytics_foundry.config import get_default_league_id, scheduler_enabled, scheduler_interval_seconds
from analytics_foundry.gold import injury as gold_injury
from analytics_foundry.gold import league as gold_league
from analytics_foundry.gold import manager_brief as gold_manager_brief
from analytics_foundry.gold import players as gold_players
from analytics_foundry.gold import recommendations as gold_recommendations

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Register NFL/Sleeper adapter, load data, and run the local job scheduler."""
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
    try:
        yield
    finally:
        if startup_catchup_task is not None:
            startup_catchup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await startup_catchup_task
        if scheduler_task is not None:
            scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler_task


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


app = FastAPI(title="Analytics Foundry API", lifespan=lifespan)
app.include_router(admin_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LeagueValidateBody(BaseModel):
    league_id: str


@app.get("/players/available")
def players_available(league_id: Optional[str] = None):
    """Available (unrostered) players. Optional query: league_id. Uses default league if omitted."""
    lid = league_id or get_default_league_id()
    gold_league.ensure_league_ingested(lid)
    return gold_players.get_available_players(league_id=lid)


@app.post("/league/validate")
def league_validate(body: LeagueValidateBody):
    """Validate league ID. Response: valid, league_id, league_name."""
    return gold_league.validate_league(body.league_id)


@app.get("/injury")
def injury_report(league_id: Optional[str] = None):
    """Injury report. Optional query: league_id. Uses default league if omitted."""
    lid = league_id or get_default_league_id()
    gold_league.ensure_league_ingested(lid)
    return gold_injury.get_injury_report(league_id=lid)


@app.get("/recommendations/waiver")
def recommendations_waiver(league_id: Optional[str] = None, limit: int = 20):
    """Waiver/add recommendations: available players with score. Shape: {recommendations: [...], league_id}. Uses default league if omitted."""
    lid = league_id or get_default_league_id()
    gold_league.ensure_league_ingested(lid)
    recs = gold_recommendations.get_waiver_recommendations(league_id=lid, limit=limit)
    return {"recommendations": recs, "league_id": lid}


@app.get("/recommendations/manager-brief")
def recommendations_manager_brief(league_id: Optional[str] = None, limit: int = 12):
    """Fantasy manager insight bundle assembled from gold recommendation models."""
    lid = league_id or get_default_league_id()
    gold_league.ensure_league_ingested(lid)
    return gold_manager_brief.get_manager_brief(league_id=lid, limit=limit)
