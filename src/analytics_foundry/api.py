"""REST API for sleeper-stream-scribe: players/available, league/validate, injury. CORS enabled."""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analytics_foundry.admin_routes import router as admin_router
from analytics_foundry.adapters import register_adapter
from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.adapters.nfl_sleeper import NFLSleeperAdapter
from analytics_foundry.gold import injury as gold_injury
from analytics_foundry.gold import league as gold_league
from analytics_foundry.gold import players as gold_players
from analytics_foundry.gold import recommendations as gold_recommendations


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Register NFL/Sleeper adapter and load persisted bronze data on startup."""
    register_adapter(NFLSleeperAdapter)
    bronze_store.load_from_disk()
    yield


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
    """Available (unrostered) players. Optional query: league_id."""
    if league_id:
        gold_league.ensure_league_ingested(league_id)
    return gold_players.get_available_players(league_id=league_id)


@app.post("/league/validate")
def league_validate(body: LeagueValidateBody):
    """Validate league ID. Response: valid, league_id, league_name."""
    return gold_league.validate_league(body.league_id)


@app.get("/injury")
def injury_report(league_id: Optional[str] = None):
    """Injury report. Optional query: league_id."""
    if league_id:
        gold_league.ensure_league_ingested(league_id)
    return gold_injury.get_injury_report(league_id=league_id)


@app.get("/recommendations/waiver")
def recommendations_waiver(league_id: Optional[str] = None, limit: int = 20):
    """Waiver/add recommendations: available players with score. Shape: {recommendations: [...], league_id}."""
    if league_id:
        gold_league.ensure_league_ingested(league_id)
    recs = gold_recommendations.get_waiver_recommendations(league_id=league_id, limit=limit)
    return {"recommendations": recs, "league_id": league_id or ""}
