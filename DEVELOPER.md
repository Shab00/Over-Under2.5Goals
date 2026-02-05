### Observability — Grafana & CI

- Grafana dashboard:
  - File: monitoring/grafana/ingestion_dashboard.json
  - Import: Grafana → + → Import → Upload JSON and select your Prometheus datasource.
  - Panels:
    - Ingestion rate by result: `rate(ingest_requests_total[5m])`
    - Skipped ratio: `(rate(ingest_requests_total{result="skipped"}[5m]) / (rate(ingest_requests_total[5m]) or 1))`

- Local smoke & metrics checks:
  - Start the app pointing at a local sqlite DB:
    DELIVERIES_DB=/tmp/test_deliveries.db make dev
  - Run the smoke test:
    TARGET=http://127.0.0.1:8000 SQLITE_DB=/tmp/test_deliveries.db ./scripts/smoke_test.sh
  - Validate metrics exposed:
    curl -s http://127.0.0.1:8000/metrics | grep 'ingest_requests_total' -n

- CI:
  - A lightweight workflow `.github/workflows/metrics-assert.yml` checks that `ingest_requests_total` exists and has `result` labels for PRs.
