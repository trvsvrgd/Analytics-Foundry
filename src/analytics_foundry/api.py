"""REST API for sleeper-stream-scribe: players/available, league/validate, injury. CORS enabled."""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analytics_foundry.admin_routes import router as admin_router, run_due_jobs_once
from analytics_foundry.adapters import register_adapter
from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.adapters.nfl_sleeper import NFLSleeperAdapter
from analytics_foundry.config import get_default_league_id, scheduler_enabled, scheduler_interval_seconds
from analytics_foundry.gold import injury as gold_injury
from analytics_foundry.gold import league as gold_league
from analytics_foundry.gold import players as gold_players
from analytics_foundry.gold import recommendations as gold_recommendations

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Register NFL/Sleeper adapter, load data, and run the local job scheduler."""
    register_adapter(NFLSleeperAdapter)
    bronze_store.load_from_disk()
    scheduler_task = None
    if scheduler_enabled():
        scheduler_task = asyncio.create_task(_scheduler_loop())
    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler_task


async def _scheduler_loop() -> None:
    interval = scheduler_interval_seconds()
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
