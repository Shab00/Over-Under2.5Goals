# Predictions API — Runbook (short)

## Symptoms / detection
- Alerts:
  - PredictionsIngestionErrorRateHigh
  - PredictionsHighSkippedRatio
  - PredictionsApiDown
- Logs: repeated sqlite OperationalError, IntegrityError, or stack traces in uvicorn.log
- Smoke tests failing (scripts/smoke_test.sh)

## Triage steps
1. Check service health & metrics:
   - curl http://localhost:8000/metrics
   - check api_ingestion_total by `result` and `source` labels
2. Check process & logs:
   - cat uvicorn.pid && ps -p $(cat uvicorn.pid) -o pid,cmd
   - tail -n 200 uvicorn.log
3. Check DB schema & lock state:
   - echo "PRAGMA table_info('deliveries');" | sqlite3 "${DELIVERIES_DB:-/tmp/pytest_deliveries.db}"
   - lsof -p $(cat uvicorn.pid) || lsof -nP -iTCP:8000 -sTCP:LISTEN

## Recovery commands
- If schema mismatch or missing columns:
  DELIVERIES_DB=/path/to/db migrations/0002_add_payload_json.sh /path/to/db
  or
  DELIVERIES_DB=/path/to/db make migrate

- If DB locked / service not starting:
  # stop server
  [ -f uvicorn.pid ] && kill "$(cat uvicorn.pid)" || pkill -f "uvicorn src.api.main"
  sleep 1
  # run migration
  DELIVERIES_DB=/path/to/db migrations/0002_add_payload_json.sh /path/to/db
  # start server
  DELIVERIES_DB=/path/to/db make dev

- If code bug introduced by last deploy:
  git revert <commit> && redeploy / restart service

## Rollback drill (local)
1. From a clean repo, check out main and create temporary test branch:
   git checkout -b rollback-drill
2. Revert the fix commit (simulate bad deploy):
   git revert <fix-commit-hash> --no-edit
3. Start server & run smoke test: make dev; make smoke (should fail)
4. Reapply fix:
   git reset --hard origin/main
   git checkout -b rollback-drill-restore
5. Start server & run smoke test (should pass)

## Verification
- make smoke returns success
- api_ingestion_total{result="persisted"} increments for successful ingest
- ingested_at column populated for new rows and backfilled for older rows
