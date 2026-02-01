#!/usr/bin/env bash
set -euo pipefail

DB_PATH=${1:-data/deliveries.db}
TIMESTAMP=$(date +%Y%m%d%H%M%S)
BACKUP="${DB_PATH}.bak.${TIMESTAMP}"

if [ ! -f "$DB_PATH" ]; then
  echo "ERROR: DB not found: $DB_PATH"
  exit 1
fi

echo "Backing up $DB_PATH -> $BACKUP"
cp "$DB_PATH" "$BACKUP"

echo "Creating deliveries_summary table if not exists..."
sqlite3 "$DB_PATH" <<'SQL'
BEGIN;
CREATE TABLE IF NOT EXISTS deliveries_summary (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id INTEGER,
  chat_id TEXT,
  sent_at TEXT NOT NULL,
  source TEXT,
  total_sent INTEGER DEFAULT 0,
  persisted_count INTEGER DEFAULT 0,
  skipped_count INTEGER DEFAULT 0,
  ingest_status_code INTEGER,
  ingest_response_json TEXT,
  payload_json TEXT
);
COMMIT;
SQL

echo "Done. deliveries_summary table ensured."
sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name='deliveries_summary';"
