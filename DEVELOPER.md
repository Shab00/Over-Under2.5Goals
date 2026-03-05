# Developer notes — local dev, testing & observability

This file collects the most common local workflows for running the API, applying migrations, and exercising observability tooling (Prometheus / Alertmanager). Keep this short and runnable.

## Environment
- Preferred DB env var: `DELIVERIES_DB`
- Compatibility: `SQLITE_DB` is supported as a fallback.
- Example test DB:
  DELIVERIES_DB=/tmp/pytest_deliveries.db

Use a virtualenv:
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

## Start the server

Foreground (use this when developing / debugging):
API_KEY="choose-a-secret" DELIVERIES_DB=/tmp/pytest_deliveries.db \
  uvicorn src.api.main:APP --reload --host 0.0.0.0 --port 8000

Background (detached; writes pid/log):
DELIVERIES_DB=/tmp/pytest_deliveries.db python -m uvicorn src.api.main:APP \
  --host 0.0.0.0 --port 8000 &> uvicorn.log & echo $! > uvicorn.pid

Stop the background server:
if [ -f uvicorn.pid ]; then kill "$(cat uvicorn.pid)" || true; rm -f uvicorn.pid; fi

Tail logs (foreground dev run writes to stdout; background writes to uvicorn.log):
tail -f uvicorn.log

Note: `make dev` is available and will start a server with a default test DB (/tmp/pytest_deliveries.db) if present — you can use that instead of the above.

## Initialize / apply migrations

Create parent directory and a new DB if needed:
mkdir -p "$(dirname /tmp/pytest_deliveries.db)"
sqlite3 /tmp/pytest_deliveries.db "PRAGMA user_version;" || true

Apply SQL migrations (idempotent pattern):
# run shell migrations then SQL
DELIVERIES_DB=/tmp/pytest_deliveries.db make migrate

Or apply a single SQL migration:
DELIVERIES_DB=/tmp/pytest_deliveries.db sqlite3 /tmp/pytest_deliveries.db < migrations/0002_add_payload_json.sql

If you prefer explicit steps:
sqlite3 /tmp/pytest_deliveries.db < migrations/0001_create_deliveries.sql
sqlite3 /tmp/pytest_deliveries.db < migrations/0002_add_payload_json.sql

## Smoke tests

Option A — use Makefile target (recommended)
# starts tests against the dev DB used by `make dev`
make smoke

Option B — use the script directly (explicit)
TARGET=http://127.0.0.1:8000 SQLITE_DB=/tmp/pytest_deliveries.db ./scripts/smoke_test.sh

Run sequence for a clean local smoke:
DELIVERIES_DB=/tmp/pytest_deliveries.db python -m uvicorn src.api.main:APP --host 0.0.0.0 --port 8000 &> uvicorn.log & echo $! > uvicorn.pid
TARGET=http://127.0.0.1:8000 SQLITE_DB=/tmp/pytest_deliveries.db ./scripts/smoke_test.sh

## Unit / integration tests
Run tests with pytest:
pytest -q

If you want to use an isolated DB for tests:
export DELIVERIES_DB=/tmp/pytest_deliveries.db
pytest -q

## Observability

Metrics endpoint:
- The app exposes Prometheus metrics at `/metrics`
- Key metric: `ingest_requests_total{result,source}`
  - `result` ∈ {`persisted`, `skipped`, `error`}
  - `source` e.g. `api-ingest`, `snapshot_etl`, `telegram-sender`

Quick checks:
# show ingest metrics
curl -s http://127.0.0.1:8000/metrics | grep ingest_requests_total -n

# check recent increases (host Prometheus query examples)
# Error rate over 5m:
sum(increase(ingest_requests_total{result="error"}[5m])) / sum(increase(ingest_requests_total[5m]))

# Skipped ratio over 5m:
sum(increase(ingest_requests_total{result="skipped"}[5m])) / max(sum(increase(ingest_requests_total[5m])), 1)

## Local Alertmanager / webhook testing

A small webhook receiver for local testing is included at `monitoring/webhook_receiver.py`.

1. Start the receiver (prints incoming POSTs)
python3 monitoring/webhook_receiver.py
# listens on 0.0.0.0:9000

2. Start Alertmanager for local testing (maps UI to host :19093)
make run-alertmanager

If Docker on Linux needs host reachability, make sure `host.docker.internal` resolves. The helper target uses `--add-host=host.docker.internal:host-gateway` where needed.

3. Send a test alert:
curl -v --http1.1 --data-binary '[{"labels":{"alertname":"TestAlert","severity":"warning","job":"predictions-api"},"annotations":{"summary":"dev test"}}]' \
  -H 'Content-Type: application/json' \
  http://127.0.0.1:19093/api/v2/alerts

Watch the webhook receiver terminal — you should see the JSON payload printed when Alertmanager delivers the notification.

## Safety & housekeeping

- Do NOT commit `monitoring/alertmanager/rendered.yml`. It's a runtime artifact produced for testing.
  Add local exclude:
  echo "monitoring/alertmanager/rendered.yml" >> .git/info/exclude

- Avoid committing secrets/real webhook URLs. Use environment variables or secret management.

- If you create a feature branch for dev tooling, squash/clean commits before merging:
  gh pr create ... && gh pr merge <branch> --squash --delete-branch

## Troubleshooting

- "unsupported scheme \"\" for URL" when starting Alertmanager:
  - Render `${SLACK_WEBHOOK_URL}` to a concrete URL (envsubst or sed) before starting Alertmanager.

- Alertmanager accepts alert (200) but webhook never appears:
  - Verify the `api_url` in `monitoring/alertmanager/rendered.yml`
  - If `api_url` is `http://127.0.0.1:9000` in the container, Alertmanager will attempt to contact itself; prefer `host.docker.internal` or container-networked receiver.

- DB row not visible after ingest:
  - Verify you're pointing to the same DB file: check `DELIVERIES_DB` or `SQLITE_DB` when starting the server and running smoke tests.

## Useful commands (one-liners)

# Start dev server (background)
DELIVERIES_DB=/tmp/pytest_deliveries.db make dev

# Run smoke test (against make dev default DB)
make smoke

# Run local webhook and Alertmanager
make run-webhook                # runs receiver on host:9000
make run-alertmanager          # runs Alertmanager on host:19093

# Prevent committing rendered.yml
echo "monitoring/alertmanager/rendered.yml" >> .git/info/exclude

# Create and apply migrations
