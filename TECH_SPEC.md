# TECH_SPEC - Analytics Foundry

## High-Level Intent

Analytics Foundry is a **personal low-code ETL workbench** that:

1. Works with **multiple data sources** via pluggable adapters (APIs, files, streams).
2. Implements a **medallion architecture**: bronze (raw), silver (cleaned/conformed), gold (business-level analytics).
3. Presents data assets and workflows as first-class UI objects: tables, models, quality rules, jobs, alerts, lineage, and local storage.
4. Lets a product-manager persona coordinate ETL work without writing SQL for routine tasks.
5. Remains **compatible with the sleeper-stream-scribe frontend** via a fixed REST API contract.

NFL/Sleeper is the first domain adapter; the same patterns extend to other personal data domains.

---

## Core Requirements

- **Pluggable source adapters** - New domains added without rewriting core pipeline logic.
- **Medallion layers** - Bronze raw ingest, silver conformed entities, gold analytics outputs.
- **Low-code workbench** - UI-first management of assets and workflows; SQL can exist underneath but is not the primary user interface.
- **Local-first storage** - No database, Docker, or multi-service orchestration required.
- **Lineage and observability** - Tables expose schema, row count, freshness, storage path, upstream assets, downstream dependents, run history, quality results, and alerts.
- **Sleeper-stream-scribe API** - Endpoints and response shapes below implemented and stable.
- **Recommendation surface** - Waiver/add and manager-brief data-product endpoints implemented and tested.

---

## Tech Stack

| Area | Choice |
|------|--------|
| Language | Python (modular, testable) |
| API | FastAPI REST; CORS for frontend on different origin |
| UI | Single static HTML + vanilla JS served by FastAPI at `/admin` |
| Storage | Local JSONL bronze files, model-output JSONL files, plus JSON/JSONL control-plane metadata |
| Ambient LLM | Local Ollama via `ambient-context-engine`; no paid cloud model required |
| Testing | pytest unit + contract + admin integration tests |
| Docs | README.md, TECH_SPEC.md, PLAN.md |

---

## API Contract (sleeper-stream-scribe compatibility)

Implement exactly so the existing frontend works without changes.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/players/available` | Available (unrostered) players. Optional query: `league_id`. Response: JSON array of player objects. |
| POST | `/league/validate` | Validate league ID. Body: `{ "league_id": "..." }`. Response: `{ "valid": true\|false, "league_id": "...", "league_name": "..." }`. |
| GET | `/injury` | Injury report. Optional query: `league_id`. Response: JSON array of `{ "player_id": string, "status": string, "updated_at"?: string }`. |
| GET | `/recommendations/waiver` | Waiver/add recommendations. Optional query: `league_id`, `limit`. Response: `{ "recommendations": [...], "league_id": "..." }`. |
| GET | `/recommendations/manager-brief` | Compact data product for fantasy-manager apps. Optional query: `league_id`, `limit`. Response: `{ "league_id": "...", "generated_at": "...", "summary": {...}, "priority_actions": [...], "models": {...} }`. |

**Player object** for `/players/available` includes at least `id`, `player_id`, `name`, `position`, `team`, `status`, `age`, and `trending`.

**League identity:** If a request includes `league_id`, the backend uses it for that request. If omitted, `FOUNDRY_DEFAULT_LEAGUE_ID` is used.

---

## Medallion Architecture

- **Bronze:** Raw ingest per source. Current persisted layout: `{FOUNDRY_DATA_DIR}/bronze/{source_id}/{table}.jsonl`.
- **Silver:** Cleaned, conformed, deduplicated canonical entity shapes.
- **Gold:** Business-level aggregates and analytics per domain. API endpoints read from gold or silver outputs.

NFL/Sleeper currently ingests broad NFL data and league-scoped data, then exposes league validation, available players, injury data, recommendations, and a manager-brief bundle assembled from gold model outputs. Sleeperstream Scribe owns the fantasy manager UI; Foundry owns the reusable data products.

---

## Workbench Control Plane

The workbench stores local metadata under `{FOUNDRY_DATA_DIR}/control_plane`.

| Object | Storage | Purpose |
|--------|---------|---------|
| Sources | `sources.json` | Saved source definitions for file/path/API onboarding and source-to-bronze lineage. |
| Jobs | `jobs.json` | Saved job definitions with kind, target, manual/interval/hourly/daily/weekly/cron-style schedule, enabled flag, retry count/delay, last status, failed attempts, and next-run timestamp. |
| Runs | `runs.jsonl` | Durable history for ingest, quality, model-preview, and model-materialization runs. |
| Quality rules | `quality_rules.json` | Saved rule definitions attached to stable table IDs. |
| Quality results | `quality_results.jsonl` | Pass/fail/error results with sample failures. |
| Alerts | `alerts.json` | In-app alert inbox for failed quality checks and failed jobs. |
| Alert delivery targets | `alert_delivery_targets.json` | Saved generic webhook and Slack-style webhook targets with severity filters and last delivery status. |
| Alert delivery logs | `alert_deliveries.jsonl` | Durable history of external alert delivery attempts. |
| Models | `models.json` | Low-code model definitions stored as JSON operations. |

Storage retention cleanup is preview-first and limited to Foundry-owned files:

- `bronze` scope deletes raw bronze table JSONL files and drops the in-memory table.
- `models` scope deletes materialized model JSONL files and clears the model's materialized-output marker.
- `run_history` scope deletes append-only `runs.jsonl`, `quality_results.jsonl`, and `alert_deliveries.jsonl` history without deleting definitions such as jobs, rules, sources, models, alerts, or delivery targets.

Stable table IDs:

- `bronze:{source_id}.{table}` for persisted raw tables.
- `silver:{name}` for conformed layer outputs.
- `gold:{name}` for business outputs.
- `model:{model_id}` for low-code model previews and materialized outputs.

Source connector templates currently supported:

- `file` for uploaded content or server-local paths in CSV, TSV, JSON, and JSONL formats.
- `api` for unauthenticated public JSON GET requests with an optional dotted records path.

Registered personal-data adapters:

- `nfl_sleeper` writes broad NFL player data and league-scoped Sleeper records to `bronze:nfl_sleeper.*`.
- `nfl_weekly_feed` writes weekly matchup, team, player, depth chart, weather, and FAAB feeds to `bronze:nfl_weekly_feed.*`.
- `ai_daily_brief` writes AI Daily Brief transcript records to `bronze:ai_daily_brief.transcripts`.
- `gmail` writes recent email records to `bronze:gmail.emails` with local Google OAuth and Gmail read-only access.
- `google_calendar` writes schedule records to `bronze:google_calendar.events` with local Google OAuth and Calendar read-only access.
- `android_messages` writes selected phone conversation exports to `bronze:android_messages.threads` through `/admin/ambient/messages/ingest`.

Ambient confidence tables:

- `silver:ambient_candidates` stores high and medium groundedness candidates with evidence, source record IDs, model, route, and review status.
- `gold:ambient_actions` stores high-confidence auto-promoted records and human-approved medium-confidence records.
- Low groundedness records are counted in evaluation runs but remain only in bronze.

Low-code model operations currently supported for preview and materialization:

- `filter`
- `select`
- `rename`
- `cast`
- `deduplicate`
- `calculate`
- `group`
- `join`
- `union`

Data quality rule templates currently supported:

- `required`
- `unique`
- `accepted_values`
- `numeric_range`
- `regex`
- `freshness`
- `row_count_drift`
- `referential`

---

## Admin API

Admin routes are unauthenticated by default for local/dev use. When `FOUNDRY_ADMIN_API_KEY` is set, `/admin` and `/admin/*` require that key through the `X-Foundry-Admin-Key` header, an `admin_key` query parameter, or the `foundry_admin_key` cookie set by visiting `/admin?admin_key=...`.

| Purpose | Endpoint / behavior |
|--------|----------------------|
| UI | GET `/admin` |
| Config | GET `/admin/config` |
| League ingest | POST `/admin/ingest/league` body `{ "league_id": "..." }` |
| Multi-league ingest | POST `/admin/ingest/leagues` body `{ "league_ids": [...] }` |
| Broad ingest | POST `/admin/ingest/broad` |
| Source templates | GET `/admin/sources/templates` |
| Sources | GET `/admin/sources` |
| Source preview | POST `/admin/sources/preview` |
| Source ingest | POST `/admin/sources/ingest` |
| Tables | GET `/admin/tables` with schema, freshness, storage, and lineage metadata |
| Table profile | GET `/admin/table-profiles/{stable_table_id}` |
| Table sample | GET `/admin/tables/{layer}/{source_or_name}[/{table}]` |
| Lineage | GET `/admin/lineage`, GET `/admin/lineage/{stable_table_id}` |
| Quality authoring context | GET `/admin/quality/authoring-context/{stable_table_id}` |
| Quality templates | GET `/admin/quality/templates` |
| Quality rules | GET/POST `/admin/quality/rules` |
| Quality run | POST `/admin/quality/run` |
| Quality results | GET `/admin/quality/results` |
| Alerts | GET `/admin/alerts`, POST `/admin/alerts/{alert_id}/ack`, GET `/admin/alerts/delivery/templates`, GET/POST `/admin/alerts/delivery-targets`, POST `/admin/alerts/delivery-targets/{target_id}/toggle`, POST `/admin/alerts/delivery-targets/{target_id}/test`, GET `/admin/alerts/deliveries` |
| Jobs | GET/POST `/admin/jobs`, GET `/admin/jobs/defaults`, POST `/admin/jobs/{job_id}/run` |
| Scheduler | GET `/admin/scheduler/status`, GET `/admin/scheduler/startup-catchup`, POST `/admin/scheduler/run-due` |
| Models | GET/POST `/admin/models`, POST `/admin/models/{model_id}/preview`, POST `/admin/models/{model_id}/materialize` |
| Model operations | GET `/admin/models/operations` |
| Ambient Ollama models | GET `/admin/ambient/ollama/models` |
| Ambient evaluation | POST `/admin/ambient/evaluate` body `{ "table_id": "...", "model"?: "...", "limit"?: 100 }` |
| Ambient review | GET `/admin/ambient/review`, POST `/admin/ambient/review/{candidate_id}/approve`, POST `/admin/ambient/review/{candidate_id}/ignore` |
| Ambient Android bridge | POST `/admin/ambient/messages/ingest` |
| Runs | GET `/admin/runs` |
| Storage | GET `/admin/storage`, POST `/admin/storage/retention/preview`, POST `/admin/storage/cleanup` |
| Diagnostics | GET `/admin/diagnostics` with storage, metadata, adapter, scheduler, and activity health |
| Metadata bundles | GET `/admin/export?include_history=false`, POST `/admin/import` body `{ "mode": "merge|replace", "bundle": {...} }` |
| Transformations | GET `/admin/transformations`, GET `/admin/transformations/{layer}/{name}` |
| Validate league | GET `/admin/league/validate?league_id=...` |

---

## Testing Standards

- Every logic change has a corresponding test.
- Default run: `python -m pytest`.
- Contract tests protect sleeper-stream-scribe API compatibility.
- Admin integration tests protect the local workbench behavior.
- Ambient tests mock Google and Ollama clients; default tests must not require live Google, Android, or Ollama services.

---

## Success Criteria

- [x] Medallion architecture in place; NFL/Sleeper flows bronze -> silver -> gold.
- [x] Pluggable adapter pattern implemented and tested.
- [x] League validation, available players, injury, and recommendation endpoints implemented and tested.
- [x] Admin UI serves local workbench surfaces.
- [x] Workbench control-plane metadata persists locally.
- [x] Tables expose schema, freshness, storage, and direct lineage.
- [x] Quality rules, results, alerts, persisted jobs, run history, and model previews are implemented and tested.
- [x] Quality rule authoring exposes schema-aware column pickers, compatible rule params, and failed-row samples.
- [x] File/API connector onboarding UI for arbitrary personal sources.
- [x] Materialized model outputs create durable local model tables.
- [x] Actual scheduler loop executes due jobs without manual clicks, with retries and failed-job alerts.
- [x] Job schedules support manual, interval, hourly, daily-at-time, weekly-at-time, and five-field cron-style expressions.
- [x] Startup seeds default weekly NFL/Sleeper, NFL weekly feed, default league, and AI Daily Brief ingest jobs, then runs overdue jobs immediately on API startup.
- [x] Retention controls expose table-file breakdowns, preview cleanup candidates, and scoped cleanup actions.
- [x] Non-in-app alert delivery through generic webhook and Slack-style webhook targets, with durable delivery logs.
- [x] Optional admin API-key authentication is disabled by default and protects `/admin` routes when configured.
- [x] Workbench metadata export/import round-trips sources, jobs, quality rules, models, alerts, alert targets, and optional history across local data roots.
- [x] Runtime diagnostics report storage writability, metadata file validity, adapter registration, scheduler state, recent failures, and open alerts.
- [x] Ambient confidence engine integrates Gmail, Google Calendar, Android selected-thread bronze ingest, local Ollama evaluation, high/medium/low routing, and approve/edit/ignore human review.

---

## Current State (Audit)

- **Repository:** Single-service FastAPI app with static Admin UI and pytest suite.
- **Implemented:** NFL/Sleeper adapter, bronze persistence, silver/gold transforms, sleeper-stream-scribe API, recommendation endpoint, table browsing, schema/freshness/storage metadata, source onboarding for files/API JSON, Gmail/Calendar/Android ambient adapters, local Ollama confidence routing, ambient human review, lineage, quality rules/results with failed-row samples, schema-aware quality authoring, alerts, webhook alert delivery, persisted jobs/runs, local due-job scheduler with cron-style scheduling, runtime diagnostics, local storage retention controls, metadata import/export bundles, low-code model previews, and materialized model outputs.
- **Runtime controls:** Due jobs run in the API process by default. Startup ensures default weekly ingest jobs exist and runs overdue work before the normal scheduler loop. Set `FOUNDRY_SCHEDULER_ENABLED=0` to disable the loop, or `FOUNDRY_SCHEDULER_INTERVAL_SECONDS` to change the polling interval.
- **Technical debt:** Source onboarding is intentionally simple; metadata bundles do not include bronze/model data files; alert delivery is webhook-based and does not include SMTP/email account setup yet.
- **Next product risk:** Avoid drifting back toward SQL-first/developer-first workflows. New features should keep tables, models, rules, jobs, alerts, lineage, and storage as the primary objects.
