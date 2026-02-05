.PHONY: up down restart reload status smoke

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

smoke:
	# adjust path and env as needed
	TARGET=http://127.0.0.1:8000 SQLITE_DB=/tmp/pytest_deliveries.db ./scripts/smoke_test.sh
