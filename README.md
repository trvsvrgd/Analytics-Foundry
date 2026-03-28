# Analytics Foundry

Generalized backend data science workbench: medallion architecture (bronze → silver → gold), pluggable source adapters, and a REST API compatible with **sleeper-stream-scribe**. Initial domain: NFL/Sleeper.

- **Constitution:** `.cursorrules`
- **Spec:** `TECH_SPEC.md`
- **Roadmap:** `PLAN.md`

## Run tests

```bash
pip install -e ".[dev]"
python -m pytest
python -m pytest --cov=analytics_foundry --cov-report=term-missing
```

Lint and types:

```bash
python -m ruff check src tests
python -m mypy src/analytics_foundry
```

## Run API (after Phase 1 implementation)

```bash
pip install -e ".[api]"
uvicorn analytics_foundry.api:app --reload
```

The app runs locally. Bronze data is stored in the **local file structure** so it persists and the Admin UI can reference it via the API.

- **Data directory:** Set `FOUNDRY_DATA_DIR` to a path (e.g. `data` or `./data`). Default is `data` (relative to the process cwd). Bronze tables are stored as `{FOUNDRY_DATA_DIR}/bronze/{source_id}/{table}.jsonl` (JSON Lines).
- **Default league:** Set `FOUNDRY_DEFAULT_LEAGUE_ID` to override the default Sleeper league used when API requests omit `league_id`. Built-in default: `1261894762944802816`.
- **Multi-tenant (optional):** Set `FOUNDRY_TENANT_ID` to isolate data under `{FOUNDRY_DATA_DIR}/tenants/{tenant_id}/`.
- **Startup:** The API validates the data directory, configures logging, loads bronze from disk, and registers the NFL/Sleeper adapter. Broad NFL sync **replaces** the bronze `players` snapshot; league-scoped sync **replaces** rows for that `league_id` in `league`, `rosters`, and `matchups` (no unbounded duplicate growth).
- **Operations:** `GET /health`, `GET /ready`, optional `GET /metrics` (set `FOUNDRY_PROMETHEUS=1`). See **DEPLOYMENT.md** for systemd and scheduling.
- **Admin UI** at `/admin` includes pipeline health, log buffer, lineage, tracked leagues (`meta/leagues.json`), tables, SQL artifacts, and ingest actions.

Frontend: set `VITE_API_BASE_URL` to this backend’s base URL (CORS enabled).

## Foundry Admin UI

A minimal admin UI is served at **`/admin`** (e.g. `http://localhost:8000/admin`). It lets you:

- Enter one or more league IDs (default pre-filled), validate, and trigger league or broad NFL ingest; support for syncing multiple leagues at once
- Browse medallion tables (bronze, silver, gold) and view sample rows
- List and view SQL transformation definitions
- See a stub "job runs" list (last syncs; no scheduler yet)

Admin API routes live under `/admin/*`. The UI is **unauthenticated** and intended for local/dev use; add auth (e.g. API key or OIDC) before exposing publicly.
