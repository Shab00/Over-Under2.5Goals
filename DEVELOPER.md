# Developer notes — local dev, testing & observability

This file collects the most common local workflows for running the API, applying migrations, and exercising observability tooling (Prometheus / Alertmanager / Grafana). Keep this short, runnable, and copy/paste friendly.

## Environment

### DB env vars
- Preferred DB env var: `DELIVERIES_DB`
- Compatibility: `SQLITE_DB` is supported as a fallback.
- Example test DB:
  - `DELIVERIES_DB=/tmp/pytest_deliveries.db`

### API auth
- For local dev we use:
  - `API_KEY="choose-a-secret"`
- The ingest endpoint expects the header:
  - `X-API-KEY: <API_KEY>`

> Tip: Do not hardcode secrets in scripts; pass them via env vars.

## Python setup (local)

Use a virtualenv:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
