# Developer Runbook

## Observability & local debugging

Prometheus and Alertmanager are configured under `monitoring/`. In Codespaces we run Prometheus in host network mode so it can scrape the app on `127.0.0.1:8000`.

To start the stack locally:
```bash
make up
```

To restart Prometheus:
```bash
make restart
# or to reload rules without restart (if lifecycle enabled):
make reload
```

To check targets, alerts and rules:
```bash
make status
```

## Rollback drill (local)

1. Identify a prior commit to test:
```bash
git log --oneline -n 6
```

2. Create a rollback branch and start the app:
```bash
git checkout -b rollback-test <COMMIT_SHA>
python -m pip install -r requirements.txt
python -m uvicorn src.api.main:APP --host 0.0.0.0 --port 8000 &> uvicorn.rollback.log & echo $! > uvicorn.rollback.pid
```

3. Run the smoke test:
```bash
TARGET=http://127.0.0.1:8000 SQLITE_DB=/tmp/pytest_deliveries.db ./scripts/smoke_test.sh
```

4. Stop the test server and return to main:
```bash
[ -f uvicorn.rollback.pid ] && kill "$(cat uvicorn.rollback.pid)" || true
git checkout main
git pull --ff-only origin main
```

Notes:
- For staging/production rollbacks follow your CI/CD provider steps; this drill validates the local behavior and the smoke test.
- If you change rules, either restart Prometheus or use the lifecycle reload endpoint (if enabled).
