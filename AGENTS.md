# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

Analytics Foundry is a single-service Python (FastAPI) backend — no database, no Docker, no multi-service orchestration. See `README.md` for run/test commands, `TECH_SPEC.md` for API contract, and `PLAN.md` for roadmap.

### Running tests

```bash
python3 -m pytest
```

All tests are self-contained with mocks/fixtures — no network or external service needed.

### Running the dev server

```bash
uvicorn analytics_foundry.api:app --host 0.0.0.0 --port 8000 --reload
```

Admin UI at `http://localhost:8000/admin`. The API fetches real data from Sleeper's public API (`https://api.sleeper.app/v1`) on ingest — no auth required but needs outbound network access.

### Caveats

- No linter is configured (no ruff, flake8, mypy, etc.). If adding one, update `pyproject.toml`.
- `pip install -e ".[api]"` installs uvicorn; without the `[api]` extra, only test deps are installed.
- Scripts install to `~/.local/bin`; use `python3 -m pytest` / `python3 -m uvicorn ...` if `~/.local/bin` is not on PATH.
- `/league/validate` calls the live Sleeper API — it will 500 for non-existent league IDs. Tests mock this out.
- `FOUNDRY_DATA_DIR` defaults to `data` (relative to cwd). Bronze JSONL files persist there across restarts.
