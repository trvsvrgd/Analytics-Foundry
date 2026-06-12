# Analytics Foundry

Personal low-code ETL workbench: medallion architecture (bronze -> silver -> gold), pluggable source adapters, local storage, data quality rules, jobs, alerts, lineage, and a REST API compatible with **sleeper-stream-scribe**. Initial domain: NFL/Sleeper.

- **Constitution:** `.cursorrules`
- **Spec:** `TECH_SPEC.md`
- **Roadmap:** `PLAN.md`

## Run tests

```bash
pip install -e .
python -m pytest
```

## Run API

```bash
pip install -e ".[api]"
uvicorn analytics_foundry.api:app --reload
```

The app runs locally. Bronze data and workbench metadata are stored in the local file structure so they persist and the Admin UI can reference them through the API.

- **Data directory:** Set `FOUNDRY_DATA_DIR` to a path (e.g. `data` or `./data`). Default is `data` (relative to the process cwd).
- **Bronze storage:** `{FOUNDRY_DATA_DIR}/bronze/{source_id}/{table}.jsonl` (JSON Lines).
- **Model output storage:** `{FOUNDRY_DATA_DIR}/models/{model_id}.jsonl` for materialized low-code model outputs.
- **Workbench storage:** `{FOUNDRY_DATA_DIR}/control_plane/*.json` and `*.jsonl` for sources, jobs, runs, rules, results, alerts, alert delivery targets/logs, and models.
- **Retention cleanup:** The Storage tab can preview and delete Foundry-owned bronze table files, materialized model files, and append-only run-history files by age and scope.
- **Metadata portability:** `/admin/export` and `/admin/import` move workbench metadata between local data roots. Bundles include saved sources, jobs, quality rules, models, alerts, and alert delivery targets, with optional run/result/delivery history.
- **Default league:** Set `FOUNDRY_DEFAULT_LEAGUE_ID` to override the default Sleeper league used when API requests omit `league_id`. Built-in default: `1261894762944802816`.
- **Scheduler:** Due jobs run in the API process by default. Jobs support manual, interval, hourly, daily-at-time, weekly-at-time, and five-field cron-style schedules evaluated in UTC. Set `FOUNDRY_SCHEDULER_ENABLED=0` to disable, or `FOUNDRY_SCHEDULER_INTERVAL_SECONDS` to change the polling interval.
- **Diagnostics:** `/admin/diagnostics` reports storage writability, metadata file health, adapter registration, scheduler state, recent failed runs, and open alerts.
- **Admin auth:** Set `FOUNDRY_ADMIN_API_KEY` to require a key for `/admin` and `/admin/*`. Supply it with the `X-Foundry-Admin-Key` header, an `admin_key` query parameter, or the cookie set by visiting `/admin?admin_key=...`.
- **Startup:** The API loads existing bronze data from that directory; new ingest appends to the same files. The Admin UI at `/admin` reads sources, tables, models, quality rules, jobs, alerts, and storage metadata through the API.

Frontend: set `VITE_API_BASE_URL` to this backend's base URL (CORS enabled).

## Foundry Admin UI

A local workbench UI is served at **`/admin`** (e.g. `http://localhost:8000/admin`). It lets you:

- Enter one or more league IDs, validate them, and trigger league or broad NFL ingest.
- Preview and ingest personal sources from uploaded files, server-local file paths, or public JSON API URLs.
- Browse medallion tables and model previews with schema, row count, freshness, storage path, sample rows, and direct lineage.
- Build and materialize low-code model definitions from JSON-backed operations such as filter, select, rename, cast, deduplicate, calculate, group, join, and union.
- Attach data quality rules to tables using schema-aware column pickers, type-aware rule params, and templates such as required field, unique key, accepted values, numeric range, regex, freshness, row count drift, and referential checks.
- Create persisted job definitions, choose manual/interval/hourly/daily/weekly/cron-style schedules, run jobs manually or through the local due-job scheduler, and inspect durable run history.
- Review in-app alerts created from failed jobs and failed quality checks, and configure generic webhook or Slack-style webhook delivery targets.
- Inspect runtime diagnostics, local storage allocation, table-file sizes, retention candidates, scoped cleanup actions, and import/export bundles for workbench metadata.
- List and view SQL transformation definitions in the advanced SQL tab.

Admin API routes live under `/admin/*`. The UI is **unauthenticated by default** for local/dev use; set `FOUNDRY_ADMIN_API_KEY` before exposing it beyond localhost or a trusted network.
