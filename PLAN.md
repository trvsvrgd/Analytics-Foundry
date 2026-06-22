# PLAN - Living Roadmap

## Completed

| Task | Verification |
|------|--------------|
| Establish Constitution (`.cursorrules`) | Read .cursorrules; principles and testing mandate present. |
| Create TECH_SPEC.md (intent, API contract, medallion, testing, success criteria) | TECH_SPEC matches mission; API table and player object match sleeper-stream-scribe. |
| Create PLAN.md (roadmap, task/verification pairs) | This file; every coding task below has a verification row. |
| **1.1** Python package layout: `src/analytics_foundry/`, `tests/`, `pyproject.toml`, pytest config | `python -m pytest` runs; placeholder/package tests pass. |
| **1.2** Medallion layer modules: `bronze/`, `silver/`, `gold/` | Import paths work; medallion layout tests pass. |
| **1.3** Pluggable adapter interface: `SourceAdapter` protocol, registry, `StubSourceAdapter` | Adapter interface and registry tests pass. |
| **1.4** NFL/Sleeper adapter for broad and league-scoped ingest | NFL adapter tests pass with mocked fixtures. |
| **1.5** Silver layer: clean/conform NFL entities | `tests/test_silver.py` passes. |
| **1.6** Gold layer: available players, league validation, injury report | API and gold tests pass. |
| **1.7** REST API: `/players/available`, `/league/validate`, `/injury` | Contract tests pass. |
| **1.8** Player response shape | Contract tests assert required fields. |
| **1.9** Recommendation endpoint | `tests/test_recommendations.py` passes. |
| **1.9a** Manager brief data product | `/recommendations/manager-brief` aggregates gold waiver, trade, injury, roster, lineup, and matchup model outputs for downstream apps; `tests/test_manager_brief.py` passes. |
| **1.10** Docs | README, TECH_SPEC, PLAN document current run/test/API behavior. |
| **2.1** Full API contract test suite | `tests/test_api_contract.py` passes. |
| **2.2** Second adapter to prove pluggability | `MockFixtureAdapter` and tests pass. |
| **2.3** SQL artifacts | `sql/`, `sql_loader.py`, and SQL artifact tests pass. |
| **2.4** Recommendation logic implementation | Waiver recommendation unit and endpoint tests pass. |
| **3.1** Workbench control-plane foundation: persisted jobs/runs, table profiles, lineage, quality rules/results, alerts, storage, and low-code model previews | `tests/test_workbench_control_plane.py` passes; full suite passes with 79 tests. |
| **3.2** Admin UI reframed as low-code workbench | `/admin` exposes Ingest, Tables, Models, Quality, Jobs, Alerts, Storage, and SQL tabs; legacy admin route tests still pass. |
| **3.3** UI-driven source onboarding for files and generic APIs | `/admin/sources/*` endpoints support preview + ingest for CSV/TSV/JSON/JSONL files and public JSON APIs; source-to-bronze lineage tested; full suite passes with 82 tests. |
| **3.4** Materialized model outputs | `/admin/models/{id}/materialize` writes durable `{FOUNDRY_DATA_DIR}/models/{model_id}.jsonl` tables; model-materialize jobs tested; full suite passes with 84 tests. |
| **3.5** Actual local scheduler loop for due jobs | API lifespan starts a local scheduler loop; `/admin/scheduler/*` supports status and forced due-run execution; tests cover due-job selection, disabled jobs, failed-job alerts, and retry delay handling; full suite passes with 87 tests. |
| **3.6** Storage controls: retention policy, table size breakdown, cleanup actions | `/admin/storage` exposes table/history file breakdowns; `/admin/storage/retention/preview` and `/admin/storage/cleanup` support scoped age-based cleanup; tests cover preview, bronze cleanup, run-history cleanup, and unrelated-file preservation; full suite passes with 89 tests. |
| **3.7** Alert delivery beyond in-app inbox: generic webhook and Slack-style webhook targets | `/admin/alerts/delivery-targets` persists delivery targets; failed jobs and quality checks trigger external delivery attempts; `/admin/alerts/deliveries` records success/failure; tests use mocked network calls; full suite passes with 92 tests. |
| **3.8** Rule authoring ergonomics: column pickers, type-aware params, sample failed rows drilldown | `/admin/quality/authoring-context/{table_id}` returns compatible columns, quality kinds, reference tables, and templates; quality results include row samples; UI uses schema-aware column/reference pickers; full suite passes with 94 tests. |
| **4.1** Authentication option for local-but-shareable admin use | `FOUNDRY_ADMIN_API_KEY` is disabled by default and protects `/admin` routes when set; tests cover unauthenticated local mode, blocked requests, header auth, query auth, UI cookie auth, and wrong-key rejection; full suite passes with 99 tests. |
| **4.2** Import/export bundle for workbench metadata | `/admin/export` and `/admin/import` round-trip saved sources, jobs, quality rules, models, alerts, alert targets, and optional history across local data roots; merge imports de-duplicate by record id; full suite passes with 102 tests. |
| **4.3** Runtime health and diagnostics endpoint | `/admin/diagnostics` reports storage writability, metadata JSON/JSONL validity, adapter registration, scheduler settings/status, recent failed runs, and open alerts; tests cover healthy and corrupted-metadata paths; full suite passes with 104 tests. |
| **5.1** Cron-like and calendar job scheduling | Jobs now support manual, interval, hourly, daily-at-time, weekly-at-time, and five-field cron-style schedules; UI exposes low-code schedule controls; tests cover daily, weekly, cron, and invalid cron behavior; full suite passes with 108 tests. |
| **6.1** Confidence and routing engine | `ambient-context-engine` provides Ollama-backed structured extraction and routing; Foundry adds Gmail, Calendar, and Android message adapters; ambient evaluation writes high/medium candidates to silver, promotes high to gold, alerts medium for review, and keeps low in bronze. Tests cover mocked adapters, routing, and approve/edit/ignore review. |
| **6.2** Default weekly ingest and startup catch-up | Startup seeds visible weekly jobs for NFL/Sleeper broad data, the default Sleeper league, the NFL weekly feed, and AI Daily Brief transcripts; overdue jobs run on API startup; `/admin/scheduler/startup-catchup` and the Admin UI banner report catch-up activity; focused control-plane tests pass. |

---

## Pending

- Build the Android companion APK once Java, Gradle, and Android SDK are installed locally.

---

## Technical Debt & Product Risks

- The scheduler runs due jobs inside the API process; startup catch-up runs missed due jobs once when the API starts, but this is still local-only and not a distributed scheduler.
- Low-code models can be previewed, materialized manually, or materialized by scheduled jobs.
- Source onboarding is intentionally simple: uploaded file content is one-shot, while server-local paths and public JSON APIs can be re-run as source-ingest jobs.
- Storage cleanup is local and file-based; it does not optimize or compact partially retained JSONL files yet.
- Alert delivery supports webhook-style targets, but not SMTP/email account setup yet.
- The SQL artifact view is intentionally secondary; new user workflows should continue to favor low-code assets.
- Android selected-thread ingest currently has a documented companion-app contract and server endpoint; APK build tooling was not available in the local Windows environment.
- Ollama evaluation requires a local Ollama service and selected local model; unavailable models queue a warning alert instead of dropping bronze records.

---

## Next Step to Execute

**Next:** Install Android tooling and turn `ambient-context-engine/android_companion` from bridge contract into a buildable sideloaded APK.
