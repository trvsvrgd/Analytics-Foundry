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

Frontend: set `VITE_API_BASE_URL` to this backend’s base URL (CORS enabled).
