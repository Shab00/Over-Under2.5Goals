# Runbook — smoke & load tests

This runbook documents how to run the smoke and small load tests for the Over-Under2.5Goals API locally and in CI.

## Local smoke test (API + DB + idempotency)
1. Activate venv (or create it if needed):
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. Start the API (backgrounded):
   ```
   python -m uvicorn src.api.main:APP --host 127.0.0.1 --port 8000 &> uvicorn.log & echo $! > uvicorn.pid
   sleep 1
   tail -n 50 uvicorn.log
   ```

3. Run the smoke script (it validates ingest, idempotency, and optionally checks data/deliveries.db):
   ```
   chmod +x scripts/smoke_test.sh
   TARGET=http://127.0.0.1:8000 SQLITE_DB=data/deliveries.db ./scripts/smoke_test.sh
   ```

4. Stop the server and cleanup:
   ```
   [ -f uvicorn.pid ] && kill "$(cat uvicorn.pid)" 2>/dev/null || true
   rm -f uvicorn.pid
   deactivate 2>/dev/null || true
   ```

## k6 load test (local, via Docker)
- Notes:
  - The k6 Docker container runs in a separate network namespace. To let the container reach a server bound to `127.0.0.1` on the host, run the container with `--network host` (Linux/Codespaces).
  - Alternately, bind uvicorn to `0.0.0.0` and use the Docker gateway IP (commonly `172.17.0.1`) as TARGET inside the container.
  - Use `grafana/k6` (the supported image).

- Run a conservative test (5 VUs, 15s) to sanity-check:
  ```
  # ensure server running (see above)
  K6_VUS=5 K6_DURATION=15s TARGET=http://127.0.0.1:8000 \
    docker run --rm -i --network host -e K6_VUS -e K6_DURATION -e TARGET grafana/k6 run - < scripts/load_ingest.js
  ```

- Full planned test (20 VUs, 30s):
  ```
  K6_VUS=20 K6_DURATION=30s TARGET=http://127.0.0.1:8000 \
    docker run --rm -i --network host -e K6_VUS -e K6_DURATION -e TARGET grafana/k6 run - < scripts/load_ingest.js
  ```

- Interpretation:
  - `http_req_failed` (rate) should be < 0.01 (1%).
  - `http_req_duration p(95)` should be within your SLA (e.g. < 500 ms).
  - `checks_succeeded` should be ≈100% (script checks status and response shape).

## CI smoke (post-deploy)
- Use the included GitHub Action (see `.github/workflows/staging-smoke.yml`) to run `scripts/smoke_test.sh` after staging is deployed.
- Action runs the smoke script and fails if the script exits non‑zero.

## Troubleshooting
- If k6 shows `connect: connection refused`:
  - Ensure uvicorn is running and listening: `ps -fp $(cat uvicorn.pid)` and `ss -ltnp | grep :8000`.
  - Use `--network host` when running the k6 Docker container, or bind uvicorn to `0.0.0.0` and target the Docker gateway IP.
- If API returns 422 for `match_id`, ensure the test payload uses a numeric `match_id` (the provided scripts do this).
- Check `uvicorn.log` for app exceptions.

