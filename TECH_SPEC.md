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

**Recommendation endpoint(s):** To be added (e.g. waiver/add suggestions). Shape defined in this repo and documented for the frontend.

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

## Current State (Audit)

- **Repository:** Greenfield. Only README.md in root; no Python or API code yet.
- **Technical debt:** N/A (no legacy code).
- **Vibe inconsistencies:** None; baseline is spec and constitution. Phase 1 is initial build to meet this spec.
