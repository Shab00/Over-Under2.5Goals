Environment
- The app reads DELIVERIES_DB (preferred). For compatibility, SQLITE_DB is supported as a fallback.
- Example: DELIVERIES_DB=/tmp/pytest_deliveries.db

Start server (background)
DELIVERIES_DB=/tmp/pytest_deliveries.db python -m uvicorn src.api.main:APP --host 0.0.0.0 --port 8000 &> uvicorn.log & echo $! > uvicorn.pid

Apply migrations (local)
DELIVERIES_DB=/tmp/pytest_deliveries.db sqlite3 /tmp/pytest_deliveries.db < migrations/0002_add_payload_json.sql

Run smoke test
TARGET=http://127.0.0.1:8000 SQLITE_DB=/tmp/pytest_deliveries.db ./scripts/smoke_test.sh
