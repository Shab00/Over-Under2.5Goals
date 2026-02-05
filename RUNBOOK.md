# RUNBOOK — Predictions Ingestion

Summary
- This runbook covers common failures for the Predictions ingestion endpoint and Prometheus alerts based on `ingest_requests_total`.
- Key metrics:
  - ingest_requests_total{result="persisted|skipped|error", source="api-ingest"}
  - rate(ingest_requests_total[5m])
  - skipped ratio: (rate(...{result="skipped"}[5m]) / (rate(...[5m]) or 1))

Symptoms (what you might see)
- Alerts:
  - PredictionsIngestionErrorRateHigh: non-zero error rate
  - PredictionsHighSkippedRatio: >50% skipped ratio over 5m
  - PredictionsApiDown: up{job="predictions-api"} == 0
- Logs/behavior:
  - Unusual number of skipped rows in ingestion responses
  - Increased HTTP 5xx on /ingest or /metrics not responding

Immediate actions (quick)
1. Check app & metrics
   - curl -s http://127.0.0.1:8000/metrics | grep 'ingest_requests_total' -n
   - curl -s http://127.0.0.1:8000/metrics | grep 'ingest_requests_total{.*result=' -n
   - curl -s http://127.0.0.1:8000/metrics | sed -n '1,200p'  # inspect other metrics

2. Check service health
   - curl -s http://127.0.0.1:8000/health || true
   - ps aux | grep uvicorn
   - docker compose ps (if running in compose)

3. Check logs
   - tail -n 200 uvicorn.log || journalctl -u predictions-api || docker logs <container>

Triage steps
1. Determine if this is metrics-only or actual data loss:
   - Run a test ingest:
     curl -s -XPOST http://127.0.0.1:8000/ingest -H 'Content-Type: application/json' -d '{"rows":[{"match_id":10000000,"prob":0.5}]}' | jq .
   - Inspect response for persisted/skipped/errors.

2. Inspect recent deploys / CI
   - gh pr list --state merged --search "observability" --json number,title,mergedAt
   - Check for recent image/tag changes or migration commits

3. If ingestion is broken and recent deploy likely caused it, follow rollback procedure (below)

Rollback procedure (fast)
- When to rollback: confirmed regression introduced by a recent commit or deploy and quick fix not available.
- Steps:
  1. Identify the last good commit on main (e.g., `git log --oneline main -n 20`).
  2. Create a rollback branch for the drill:
     git fetch origin
     git checkout -b rollback-drill origin/main
  3. Revert the suspect commit (example):
     git revert <commit-sha> --no-edit
     # or check out the known-good commit and push a fix-release
  4. Run locally with the reverted code:
     DELIVERIES_DB=/tmp/test_deliveries.db make dev
  5. Run smoke test:
     TARGET=http://127.0.0.1:8000 SQLITE_DB=/tmp/test_deliveries.db ./scripts/smoke_test.sh
  6. If smoke passes, deploy rollback (your deployment process) and notify stakeholders.

Postmortem checklist (after recovery)
- Record timeline, root cause, and corrective actions
- Add tests/CI checks to prevent similar regressions
- Tune alert thresholds if noisy

Contacts & escalation
- On-call: <pagerduty_or_slack_oncall_placeholder>
- Team: @backend, @platform (replace with your real channels)
- Escalation order: primary on-call → secondary → team lead → incident manager

Notes
- If in doubt, prefer safety: revert to a known good commit and keep the system functional while investigating.
- Update this runbook after any procedural changes or postmortem findings.
