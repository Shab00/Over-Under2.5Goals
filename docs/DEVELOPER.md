# Developer notes — Running, smoke tests, observability & rollback

## Run locally (Codespace / dev machine)
Start the app (no autoreload recommended for repeatable tests):
```bash
# stop any existing instance first
[ -f uvicorn.pid ] && kill "$(cat uvicorn.pid)" 2>/dev/null || true
rm -f uvicorn.pid uvicorn.log || true

# start the app using a test DB
export DELIVERIES_DB=/tmp/pytest_deliveries.db
python -m uvicorn src.api.main:APP --host 127.0.0.1 --port 8000 &> uvicorn.log & echo $! > uvicorn.pid
sleep 1
tail -n 80 uvicorn.log
