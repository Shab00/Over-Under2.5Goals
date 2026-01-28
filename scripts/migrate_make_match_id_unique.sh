#!/usr/bin/env bash
set -euo pipefail

DB="data/deliveries.db"

if [ ! -f "$DB" ]; then
  echo "Database not found at $DB"
  exit 1
fi

echo "Backing up DB to ${DB}.bak (if not already backed up)..."
cp -n "$DB" "${DB}.bak" || true

echo "Running migration to deduplicate by match_id and create UNIQUE index..."

sqlite3 "$DB" <<'SQL'
PRAGMA writable_schema = OFF;
PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

-- Create a new table with UNIQUE(match_id). Keep columns consistent with your app.
CREATE TABLE IF NOT EXISTS deliveries_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    received_at TEXT,
    ingested_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id)
);

-- Insert rows in an order such that the first row for each match_id is the one we want to keep:
-- ORDER BY match_id ASC, (received_at or ingested_at) DESC, id DESC so the latest row per match_id is encountered first.
-- INSERT OR IGNORE ensures subsequent rows for same match_id (violating UNIQUE) are ignored.
INSERT OR IGNORE INTO deliveries_new (match_id, source, payload_json, received_at, ingested_at)
SELECT match_id, source, payload_json,
       COALESCE(received_at, ingested_at) AS received_at,
       ingested_at
FROM deliveries
ORDER BY match_id ASC, COALESCE(received_at, ingested_at) DESC, id DESC;

-- Replace table
DROP TABLE deliveries;
ALTER TABLE deliveries_new RENAME TO deliveries;

-- Recreate indexes (including the new unique index)
CREATE INDEX IF NOT EXISTS idx_deliveries_received_at ON deliveries(received_at);
CREATE INDEX IF NOT EXISTS idx_deliveries_ingested_at ON deliveries(ingested_at);
CREATE INDEX IF NOT EXISTS idx_deliveries_match_id ON deliveries(match_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_match_id ON deliveries(match_id);

COMMIT;
PRAGMA foreign_keys = ON;
SQL

echo "Migration complete. New UNIQUE index idx_unique_match_id created (if not already present)."
