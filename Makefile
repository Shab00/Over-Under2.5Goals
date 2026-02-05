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
	@echo "  make migrate   - apply SQL migrations to DELIVERIES_DB (local only)"

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
	# apply migrations to DELIVERIES_DB (LOCAL USE)
	test -n "${DELIVERIES_DB}" || (echo "Set DELIVERIES_DB env var" && exit 1)
	for f in migrations/*.sql; do echo "Applying $$f"; sqlite3 "${DELIVERIES_DB}" < "$$f"; done
