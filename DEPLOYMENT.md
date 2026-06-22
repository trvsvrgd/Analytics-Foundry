# Deploying Analytics Foundry (self-hosted)

## Requirements

- Python 3.10+
- `pip install -e ".[api]"` on the host
- Network egress to `https://api.sleeper.app` if you use live NFL/Sleeper ingest

## Environment variables

| Variable | Purpose |
|----------|---------|
| `FOUNDRY_DATA_DIR` | Bronze JSONL root (default `data` under process cwd). Empty = in-memory only. |
| `FOUNDRY_DEFAULT_LEAGUE_ID` | Default Sleeper league when API omits `league_id`. |
| `FOUNDRY_TENANT_ID` | Optional; data root becomes `{FOUNDRY_DATA_DIR}/tenants/{id}/`. |
| `FOUNDRY_LOG_LEVEL` | `INFO` (default), `DEBUG`, etc. |
| `FOUNDRY_LOG_JSON` | `1` / `true` for one JSON object per log line on stderr. |
| `FOUNDRY_PROMETHEUS` | `1` / `true` to expose `GET /metrics` (Prometheus text). |
| `FOUNDRY_AUDIT_LOG` | `1` / `true` to log each HTTP path at INFO (basic audit trail). |
| `FOUNDRY_SLEEPER_CACHE_TTL_SECONDS` | Cache TTL for `GET /players/nfl` snapshot (default `3600`; `0` disables). |
| `FOUNDRY_SLEEPER_MIN_INTERVAL_SECONDS` | Minimum seconds between Sleeper HTTP calls (default `0`). |
| `FOUNDRY_RETENTION_DAYS` | Documented hook for future pruning; no automatic deletion yet. |

## Process manager (systemd)

Example unit (adjust paths and user):

```ini
[Unit]
Description=Analytics Foundry API
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/analytics-foundry
Environment=FOUNDRY_DATA_DIR=/var/lib/foundry/data
Environment=FOUNDRY_LOG_LEVEL=INFO
ExecStart=/opt/analytics-foundry/.venv/bin/uvicorn analytics_foundry.api:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Reload and enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now analytics-foundry.service
```

Uvicorn handles SIGTERM for graceful shutdown; the app logs shutdown on exit.

## Scheduled ingest

There is no built-in cron yet. Use **systemd timers** or **cron** to call admin endpoints, for example:

```bash
curl -sS -X POST http://127.0.0.1:8000/admin/ingest/broad
curl -sS -X POST http://127.0.0.1:8000/admin/ingest/league -H 'Content-Type: application/json' -d '{"league_id":"YOUR_LEAGUE_ID"}'
```

## Health checks

- **Liveness:** `GET /health` → `{"status":"ok"}`.
- **Readiness:** `GET /ready` → 200 when the NFL adapter is registered (after app lifespan startup); 503 otherwise.

## Security

- Admin UI and `/admin/*` APIs are **unauthenticated** by default for local use.
- Do not expose `/admin` or `/metrics` publicly without reverse-proxy auth (API key, mTLS, VPN, etc.).
