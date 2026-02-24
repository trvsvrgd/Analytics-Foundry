# PLAN — Living Roadmap

## Completed

| Task | Verification |
|------|--------------|
| Establish Constitution (`.cursorrules`) | Read .cursorrules; principles and testing mandate present. |
| Create TECH_SPEC.md (intent, API contract, medallion, testing, success criteria) | TECH_SPEC matches mission; API table and player object match sleeper-stream-scribe. |
| Create PLAN.md (roadmap, task/verification pairs) | This file; every coding task below has a verification row. |
| **1.1** Python package layout: `src/analytics_foundry/`, `tests/`, `pyproject.toml`, pytest config | `python -m pytest` runs; 2 tests pass (placeholder + package import). |
| **1.2** Medallion layer modules: `bronze/`, `silver/`, `gold/` under `analytics_foundry` | Imports work; `tests/test_medallion_layout.py` (4 tests) pass; layout matches TECH_SPEC. |
| **1.3** Pluggable adapter interface: `SourceAdapter` protocol, registry, `StubSourceAdapter` | `tests/test_adapters.py` (4 tests) pass; interface exists; stub registered/instantiated. |

---

## Pending

### Phase 1 — Foundation & NFL Adapter (Initial Build)

| # | Coding Task | Verification / Test Task |
|---|-------------|---------------------------|
| 1.1 | Python package layout: `src/` (or equivalent), `tests/`, `pyproject.toml` or `requirements.txt`, `pytest` config | Run `pytest`; at least one placeholder test passes. |
| 1.2 | Medallion layer modules: bronze, silver, gold (packages or subpackages); clear naming (e.g. `bronze/`, `silver/`, `gold/` or domain-scoped) | Import paths work; TECH_SPEC medallion description matches layout. |
| 1.3 | Pluggable adapter interface: base adapter / protocol for “source → bronze”; one concrete adapter stub | Unit test: adapter interface exists; stub can be registered/instantiated. |
| 1.4 | NFL/Sleeper adapter: (a) broad ingest — players/injuries to bronze (no league_id); (b) league-scoped ingest — league_id → league/rosters/matchups to bronze. API layer: when request includes league_id, ensure league in bronze/silver (lazy fetch if missing), then serve from gold. | Test: broad ingest (fixture/mock) lands in bronze; test: league-scoped ingest with league_id lands in bronze. |
| 1.5 | Silver layer: clean/conform NFL entities (players, leagues, rosters, injuries); schema and naming consistent | Test: silver output conforms to expected schema; dedup/cleaning logic tested. |
| 1.6 | Gold layer: views/tables for “available players,” “league validation,” “injury report” per league | Test: gold outputs match shapes required by API (player object, league validation, injury array). |
| 1.7 | REST API: GET `/players/available`, POST `/league/validate`, GET `/injury`; CORS enabled; read from gold/silver | Contract/integration tests: each endpoint returns correct shape and status; CORS headers present. |
| 1.8 | Player response: `id`/`player_id`, `name`, `position`, `team`, `status`, `age`, `trending` per TECH_SPEC | Test: response JSON schema or fixture matches; frontend normalization (player_id → id) satisfied. |
| 1.9 | Recommendation endpoint: stub (e.g. GET `/recommendations/waiver` or similar) with documented shape | Stub returns 200 + documented JSON shape; test asserts shape; TECH_SPEC/API docs updated. |
| 1.10 | Docs: README (how to run API, run tests); TECH_SPEC and PLAN updated with “current state” | README has `pytest` and API run commands; PLAN “Completed” updated for Phase 1 items as done. |

### Phase 2 — Hardening & Extensibility (After Phase 1)

| # | Coding Task | Verification / Test Task |
|---|-------------|---------------------------|
| 2.1 | Contract test suite: full sleeper-stream-scribe API contract (all three endpoints + optional league_id) | Pytest contract tests; run on CI. |
| 2.2 | Second adapter (optional second domain or mock) to prove pluggability | Test: second adapter runs through bronze without changing core pipeline. |
| 2.3 | SQL-heavy refactor: move transforms to SQL where applicable (e.g. Delta/Spark SQL or raw SQL scripts) | Tests for SQL artifacts; medallion still bronze → silver → gold. |
| 2.4 | Recommendation logic (waiver/add) implementation if not done in Phase 1 | Unit tests for logic; integration test for recommendation endpoint. |

---

## Technical Debt & Vibe Inconsistencies (Audit)

- **Current:** Greenfield repo. No legacy code; no existing technical debt.
- **Risks:** Introducing logic without tests; adding endpoints that drift from TECH_SPEC API contract; monolith modules instead of modular adapters.
- **Phase 1 focus:** Build to spec from day one—modular Python, medallion layers, adapter pattern, and tests for every logical change. No “we’ll add tests later.”

---

## Next Step to Execute

**Next:** **1.4 — NFL/Sleeper adapter.**  
Implement NFL/Sleeper adapter: ingest league, players, rosters (and injuries if available) into bronze. Verification: unit or integration test that Sleeper data (or fixture) lands in bronze.
