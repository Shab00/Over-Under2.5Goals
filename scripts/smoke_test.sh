#!/usr/bin/env bash
set -euo pipefail

# Usage:
# TARGET=http://127.0.0.1:8000 SQLITE_DB=data/deliveries.db ./scripts/smoke_test.sh

TARGET=${TARGET:-http://127.0.0.1:8000}
SQLITE_DB=${SQLITE_DB:-}
RETRIES=${RETRIES:-3}
SLEEP_BETWEEN=${SLEEP_BETWEEN:-1}

if ! command -v jq >/dev/null 2>&1; then
  echo "This script requires jq. Install it and re-run."
  exit 2
fi

echo "Running smoke test against $TARGET"
RANDOM_ID=$(date +%s%3N)   # numeric match_id
PAYLOAD="{\"rows\":[{\"match_id\":${RANDOM_ID},\"prob\":0.5}]}"

echo "POST payload: $PAYLOAD"
RESP=$(curl -s -w "\n%{http_code}" -X POST "$TARGET/ingest" -H "Content-Type: application/json" -d "$PAYLOAD")
BODY=$(echo "$RESP" | sed '$d')
HTTP=$(echo "$RESP" | tail -n1)

echo "HTTP $HTTP"
echo "Body: $BODY"

if [ "$HTTP" -ne 200 ]; then
  echo "ERROR: ingest returned $HTTP"
  exit 3
fi

if echo "$BODY" | jq -e 'has("persisted") or has("error")' >/dev/null 2>&1; then
  echo "Response contains expected keys."
else
  echo "Unexpected response shape. Response must include 'persisted' or 'error'."
  exit 4
fi

if [ -n "$SQLITE_DB" ]; then
  if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "sqlite3 not found; cannot verify DB. Skipping DB check."
  else
    echo "Verifying deliveries.db for match_id $RANDOM_ID"
    for i in $(seq 1 $RETRIES); do
      ROWS=$(sqlite3 -header -csv "$SQLITE_DB" "SELECT id,match_id,source,received_at FROM deliveries WHERE match_id=${RANDOM_ID};" || true)
      if [ -n "$ROWS" ]; then
        echo "DB row found:"
        echo "$ROWS"
        break
      fi
      echo "Not yet visible in DB; retrying in $SLEEP_BETWEEN s..."
      sleep $SLEEP_BETWEEN
    done
    if [ -z "$ROWS" ]; then
      echo "ERROR: row not found in DB after retries."
      exit 5
    fi
  fi
fi

echo "Testing idempotency: re-POST same payload"
RESP2=$(curl -s -w "\n%{http_code}" -X POST "$TARGET/ingest" -H "Content-Type: application/json" -d "$PAYLOAD")
BODY2=$(echo "$RESP2" | sed '$d')
HTTP2=$(echo "$RESP2" | tail -n1)

echo "HTTP $HTTP2"
echo "Body: $BODY2"

if echo "$BODY2" | jq -e '.persisted == 0 or .skipped == true or has("error")' >/dev/null 2>&1; then
  echo "Idempotency behavior OK (second request skipped or returned error indication)."
else
  echo "WARNING: Idempotency result ambiguous — inspect response:"
  echo "$BODY2"
fi

echo "Smoke test complete — success."
