# Analytics Foundry

Generalized backend data science workbench: medallion architecture (bronze → silver → gold), pluggable source adapters, and a REST API compatible with **sleeper-stream-scribe**. Initial domain: NFL/Sleeper.

- **Constitution:** `.cursorrules`
- **Spec:** `TECH_SPEC.md`
- **Roadmap:** `PLAN.md`

## Run tests

```bash
pip install -e .
python -m pytest
```

## Run API (after Phase 1 implementation)

```bash
pip install -e ".[api]"
uvicorn analytics_foundry.api:app --reload
```

The app runs locally. Bronze data is stored in the **local file structure** so it persists and the Admin UI can reference it via the API.

- **Data directory:** Set `FOUNDRY_DATA_DIR` to a path (e.g. `data` or `./data`). Default is `data` (relative to the process cwd). Bronze tables are stored as `{FOUNDRY_DATA_DIR}/bronze/{source_id}/{table}.jsonl` (JSON Lines).
- **Startup:** The API loads existing bronze data from that directory; new ingest appends to the same files. The Admin UI at `/admin` reads this data through the API (tables list and sample endpoints).

Frontend: set `VITE_API_BASE_URL` to this backend’s base URL (CORS enabled).

## Foundry Admin UI

A minimal admin UI is served at **`/admin`** (e.g. `http://localhost:8000/admin`). It lets you:

- Enter a league ID, validate it, and trigger league or broad NFL ingest
- Browse medallion tables (bronze, silver, gold) and view sample rows
- List and view SQL transformation definitions
- See a stub "job runs" list (last syncs; no scheduler yet)

Admin API routes live under `/admin/*`. The UI is **unauthenticated** and intended for local/dev use; add auth (e.g. API key or OIDC) before exposing publicly.
