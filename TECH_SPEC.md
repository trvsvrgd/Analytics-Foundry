# TECH_SPEC — Analytics Foundry

## High-Level Intent

Analytics Foundry is a **generalized backend data science workbench** that:

1. Works with **multiple data sources** via pluggable adapters (APIs, files, streams).
2. Implements a **complete medallion architecture**: bronze (raw), silver (cleaned/conformed), gold (business-level aggregates and analytics).
3. Supports **data science and analytics across domains** (e.g. NFL, other sports, finance, operations), each with its own pipelines and gold outputs while sharing medallion patterns and tooling.
4. Remains **compatible with the sleeper-stream-scribe frontend** via a fixed REST API contract.

NFL/Sleeper is the **first domain adapter**; the same patterns extend to other domains.

---

## Core Requirements

- **Pluggable source adapters** — New domains added without rewriting core pipeline logic.
- **Medallion layers** — Bronze (raw ingest), silver (cleaned/conformed), gold (analytics/aggregates). SQL-heavy; schema and table naming clear and consistent.
- **Unity Catalog–friendly, AWS/Databricks-ready** — Layouts and naming suitable for cloud and Unity Catalog where applicable.
- **Sleeper-stream-scribe API** — Endpoints and response shapes below implemented and stable.
- **Recommendation surface** — Waiver/add (or equivalent) recommendation endpoint(s) either implemented or stubbed and documented for the frontend.

---

## Tech Stack

| Area | Choice |
|------|--------|
| Language | Python (modular, testable) |
| Data | SQL-heavy; medallion; Unity Catalog–aware; AWS/Databricks-ready |
| API | REST; CORS for frontend on different origin; base URL via frontend `VITE_API_BASE_URL` |
| Testing | pytest; unit + contract/integration tests for API |
| Docs | TECH_SPEC.md, PLAN.md; API and medallion layers documented here |

---

## API Contract (sleeper-stream-scribe compatibility)

Implement **exactly** so the existing frontend works without changes.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/players/available` | Available (unrostered) players. Optional query: `league_id`. Response: JSON array of player objects. |
| POST | `/league/validate` | Validate league ID. Body: `{ "league_id": "..." }`. Response: `{ "valid": true\|false, "league_id": "...", "league_name": "..." }`. |
| GET | `/injury` | Injury report (live). Optional query: `league_id`. Response: JSON array of `{ "player_id": string, "status": string, "updated_at"?: string }`. |

**Player object** (for `/players/available`): must include at least `id` (or `player_id`; frontend normalizes `player_id` → `id`), `name`, `position`, `team`, `status`, `age` (number or null), `trending` (number or null). All string fields strings; omit or null for missing values.

**Recommendation endpoint(s):** GET `/recommendations/waiver` — optional query: `league_id`, `limit`. Response: `{ "recommendations": [ { "player_id", "name", "position", "team", "score" } ], "league_id": "..." }`. Score is numeric (e.g. trending); frontend can sort by score for waiver/add suggestions.

**League identity:** The user's Sleeper league is provided by the frontend on each request (query param or body). No backend "insert" of league is required. If the frontend sends `league_id`, the backend uses it for that request only (stateless).

**Data scope (Sleeper/NFL):**
- **Broad NFL:** Players, injuries — ingested without `league_id`. Periodic or on startup; no user league required.
- **League-specific:** League metadata, rosters, matchups — ingested only when `league_id` is present (on-demand or cached). When a request includes `league_id`, the backend ensures that league's data is in bronze/silver (lazy fetch if missing), then serves from gold.

---

## Medallion Architecture

- **Bronze:** Raw ingest per source (e.g. Sleeper API, files). Schema: source-specific; append-only where applicable.
- **Silver:** Cleaned, conformed, deduplicated. Canonical entity shapes (e.g. players, leagues, injuries). Domain-agnostic where possible.
- **Gold:** Business-level aggregates and analytics per domain (e.g. NFL: available players, injury report, league validation). API reads from gold (or silver) views/tables.

NFL/Sleeper adapter: ingest Sleeper/NFL data through bronze → silver → gold; serve league validation, available players, and injury data from gold/silver.

---

## Testing Standards

- **Every logic change** has a corresponding test.
- **Default run:** `pytest`
- **Unit tests:** Pure logic, transforms, adapters.
- **Contract / integration tests:** The three endpoints above (and any recommendation endpoints) so sleeper-stream-scribe compatibility is regression-tested.
- **CI:** Plan for `pytest` as the gate; command documented in README and PLAN.

---

## Success Criteria (when the vibe is "passing")

- [ ] Medallion architecture in place; at least one data source (NFL/Sleeper) flows bronze → silver → gold.
- [ ] Multiple data sources supported by design (pluggable adapters); at least NFL implemented.
- [ ] League validation, available players, and injury endpoints implemented, documented, and tested.
- [ ] Recommendation endpoint(s) implemented or clearly stubbed and documented for future work.
- [ ] `pytest` runs and passes; TECH_SPEC and PLAN updated as the system evolves.

---

## Foundry Admin UI

- **Purpose:** Single place to interact with the foundry: league ID + ingest, medallion table browse/sample, view SQL transformations, and (stub) job runs.
- **URL:** Served at `/admin` by the same FastAPI app (e.g. `http://localhost:8000/admin`).
- **Tech:** Single HTML + vanilla JS that calls admin API endpoints under `/admin/*`.
- **Security:** Admin routes are **unauthenticated** for local/dev. Document that auth (e.g. API key or OIDC) should be added before exposing the admin UI or API publicly.

**Admin API (summary):**

| Purpose | Endpoint / behavior |
|--------|----------------------|
| League ingest | POST `/admin/ingest/league` body `{ "league_id": "..." }` |
| Broad ingest | POST `/admin/ingest/broad` |
| List tables | GET `/admin/tables` — bronze from store; silver/gold as fixed list with row_count |
| Sample table | GET `/admin/tables/{layer}/{source_or_name}[/{table}]` (bronze: source_id + table; gold: name) |
| List transformations | GET `/admin/transformations` |
| View transformation | GET `/admin/transformations/{layer}/{name}` |
| Job runs (stub) | GET `/admin/runs` |
| Validate league (UI) | GET `/admin/league/validate?league_id=...` |

---

## Local data storage

The app is intended to run on a **local machine**. Bronze (raw) data is persisted under a configurable data directory so the UI (via the API) can reference it and data survives restarts.

- **Env:** `FOUNDRY_DATA_DIR` — path to the data root (default `data`, relative to process cwd). If unset or empty, bronze is in-memory only (e.g. for tests).
- **Layout:** `{FOUNDRY_DATA_DIR}/bronze/{source_id}/{table}.jsonl` — one JSON object per line (JSON Lines), append-only.
- **Startup:** The FastAPI app calls `bronze_store.load_from_disk()` on startup so existing files are loaded into memory; `append_raw` continues to append to the same files.

---

## Current State (Audit)

- **Repository:** Greenfield. Only README.md in root; no Python or API code yet.
- **Technical debt:** N/A (no legacy code).
- **Vibe inconsistencies:** None; baseline is spec and constitution. Phase 1 is initial build to meet this spec.
