.PHONY: run smoke k6 logs stop clean

run:
	# run the app in background and capture logs/pid
	uvicorn src.api.main:APP --host 127.0.0.1 --port 8000 &> uvicorn.log & echo $$! > uvicorn.pid

smoke:
	# run the existing smoke script against the repo DB
	TARGET=http://127.0.0.1:8000 SQLITE_DB=data/deliveries.db ./scripts/smoke_test.sh

k6:
	# example small k6 run (requires docker + network host)
	# VUS and DURATION can be set in environment, e.g. VUS=5 DURATION=15s make k6
	docker run --rm -i --network host -e VUS -e DURATION -e TARGET grafana/k6 run - < scripts/load_ingest.js

logs:
	@tail -n 200 uvicorn.log || true

stop:
	@if [ -f uvicorn.pid ]; then kill $$(cat uvicorn.pid) 2>/dev/null || true; fi

clean:
	rm -f uvicorn.pid uvicorn.log /tmp/sanity_deliveries.db || true
