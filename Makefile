.PHONY: help up down restart reload status run dev smoke migrate

help:
	@echo "Targets:"
	@echo "  make up        - docker compose up -d"
	@echo "  make down      - docker compose down"
	@echo "  make restart   - restart prometheus stack"
	@echo "  make reload    - reload prometheus config (requires lifecycle flag)"
	@echo "  make status    - show prometheus targets & alerts"
	@echo "  make run       - run uvicorn in foreground (set DELIVERIES_DB)"
	@echo "  make dev       - run uvicorn in background (writes uvicorn.pid)"
	@echo "  make smoke     - run local smoke test against server"
	@echo "  make migrate   - apply migrations to DELIVERIES_DB (local only)"

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart prometheus || (docker compose down && docker compose up -d)

reload:
	# Requires --web.enable-lifecycle in Prometheus command
	curl -s -XPOST http://127.0.0.1:9090/-/reload || true

status:
	curl -s 'http://127.0.0.1:9090/api/v1/targets' | jq '.data.activeTargets[] | {scrapeUrl:.scrapeUrl,health:.health,lastError:.lastError}'
	curl -s 'http://127.0.0.1:9090/api/v1/alerts' | jq .

run:
	# Run uvicorn in foreground (set DELIVERIES_DB or SQLITE_DB env var)
	DELIVERIES_DB=${DELIVERIES_DB} python -m uvicorn src.api.main:APP --host 0.0.0.0 --port 8000

dev:
	# start in background and write pid/log
	DELIVERIES_DB=${DELIVERIES_DB:-/tmp/pytest_deliveries.db} python -m uvicorn src.api.main:APP --host 0.0.0.0 --port 8000 &> uvicorn.log & echo $$! > uvicorn.pid

smoke:
	# run smoke test (expects scripts/smoke_test.sh)
	TARGET=${TARGET:-http://127.0.0.1:8000} SQLITE_DB=${SQLITE_DB:-/tmp/pytest_deliveries.db} ./scripts/smoke_test.sh

migrate:
	# apply shell migrations first (idempotent)
	test -n "${DELIVERIES_DB}" || (echo "Set DELIVERIES_DB env var" && exit 1)
	for f in migrations/*.sh; do echo "Running $$f"; bash "$$f" "${DELIVERIES_DB}"; done
	# apply any remaining SQL migrations (best-effort, ignore parse errors)
	for f in migrations/*.sql; do echo "Applying $$f"; sqlite3 "${DELIVERIES_DB}" < "$$f" || echo "SQL migration $$f failed or already applied; continuing"; done

# Local helpers for observability testing (non-destructive additions)

# Start Alertmanager for local testing; maps Alertmanager UI to host port 19093
# Use host.docker.internal on Docker Desktop if the webhook receiver runs on the host.
# This target maps Alertmanager UI to 19093 to avoid colliding with local 9093 instances.
run-alertmanager:
	docker run --rm -p 19093:9093 \
	  -v "$(PWD)/monitoring/alertmanager:/etc/alertmanager" \
	  -e SLACK_WEBHOOK_URL='http://host.docker.internal:9000' \
	  prom/alertmanager:latest \
	  --config.file=/etc/alertmanager/alertmanager.yml

# Start the tiny webhook receiver (forwards POST body to stdout) — runs in foreground
run-webhook:
	python3 monitoring/webhook_receiver.py
