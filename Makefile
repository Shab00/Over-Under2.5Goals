DELIVERIES_DB ?= /tmp/pytest_deliveries.db
SQLITE_DB ?= /tmp/pytest_deliveries.db
TARGET ?= http://127.0.0.1:8000
API_URL ?= http://127.0.0.1:8000

.PHONY: help up down restart reload status run dev smoke migrate \
        urls pipeline-run send-weekly env-check

help:
	@echo "Targets:"
	@echo "  make up           - docker compose up -d"
	@echo "  make down         - docker compose down"
	@echo "  make restart      - restart prometheus stack"
	@echo "  make reload       - reload prometheus config (requires lifecycle flag)"
	@echo "  make status       - show prometheus targets & alerts"
	@echo "  make urls         - print local service URLs"
	@echo "  make run          - run uvicorn in foreground"
	@echo "  make dev          - run uvicorn in background (writes uvicorn.pid)"
	@echo "  make smoke        - run local smoke test against server"
	@echo "  make migrate      - apply migrations to DELIVERIES_DB (local only)"
	@echo "  make pipeline-run - run weekly pipeline locally (scrape→train→snapshot→deliver)"
	@echo "  make send-weekly  - send weekly telegram digest"
	@echo ""
	@echo "Env vars (common):"
	@echo "  API_KEY, DELIVERIES_DB, SQLITE_DB, TARGET, API_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"

up:
	docker compose up -d
	@$(MAKE) urls

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

urls:
	@echo ""
	@echo "API:        http://127.0.0.1:8000"
	@echo "Prometheus: http://127.0.0.1:9090"
	@echo "Grafana:    http://127.0.0.1:3001 (admin/admin)"
	@echo ""

run:
	# Run uvicorn in foreground
	DELIVERIES_DB=$(DELIVERIES_DB) API_KEY=$(API_KEY) \
	  python -m uvicorn src.api.main:APP --host 0.0.0.0 --port 8000

dev:
	# start in background and write pid/log
	DELIVERIES_DB=$(DELIVERIES_DB) API_KEY=$(API_KEY) \
	  python -m uvicorn src.api.main:APP --host 0.0.0.0 --port 8000 &> uvicorn.log & echo $$! > uvicorn.pid

smoke:
	# run smoke test (expects scripts/smoke_test.sh)
	API_KEY=$(API_KEY) TARGET=$(TARGET) SQLITE_DB=$(SQLITE_DB) \
	  ./scripts/smoke_test.sh

migrate:
	# apply shell migrations first (idempotent)
	test -n "$(DELIVERIES_DB)" || (echo "Set DELIVERIES_DB env var" && exit 1)
	for f in migrations/*.sh; do echo "Running $$f"; bash "$$f" "$(DELIVERIES_DB)"; done
	# apply any remaining SQL migrations (best-effort, ignore parse errors)
	for f in migrations/*.sql; do echo "Applying $$f"; sqlite3 "$(DELIVERIES_DB)" < "$$f" || echo "SQL migration $$f failed or already applied; continuing"; done

# --- Weekly pipeline ---

env-check:
	@python3 -c 'import sys; print("python:", sys.version.split()[0])'
	@echo "DELIVERIES_DB=$(DELIVERIES_DB)"
	@echo "SQLITE_DB=$(SQLITE_DB)"
	@echo "TARGET=$(TARGET)"
	@echo "API_URL=$(API_URL)"
	@echo "API_KEY=$${API_KEY:+<set>}$${API_KEY:-<unset>}"
	@echo "TELEGRAM_BOT_TOKEN=$${TELEGRAM_BOT_TOKEN:+<set>}$${TELEGRAM_BOT_TOKEN:-<unset>}"
	@echo "TELEGRAM_CHAT_ID=$${TELEGRAM_CHAT_ID:-<unset>}"

pipeline-run:
	./jobs/run_weekly_pipeline.sh

send-weekly:
	# wrapper calls scripts/send_telegram_digest.py
	python3 jobs/deliver_telegram.py

# Local helpers for observability testing (existing)

run-alertmanager:
	docker run --rm -p 19093:9093 \
	  -v "$(PWD)/monitoring/alertmanager:/etc/alertmanager" \
	  -e SLACK_WEBHOOK_URL='http://host.docker.internal:9000' \
	  prom/alertmanager:latest \
	  --config.file=/etc/alertmanager/alertmanager.yml

run-webhook:
	python3 monitoring/webhook_receiver.py
