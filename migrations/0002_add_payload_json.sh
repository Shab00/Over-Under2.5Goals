#!/usr/bin/env bash
set -euo pipefail

DB="${1:-/tmp/pytest_deliveries.db}"

if [ ! -f "$DB" ]; then
  echo "DB not found: $DB"
  exit 1
fi

echo "Checking columns in $DB..."
cols=$(sqlite3 "$DB" "PRAGMA table_info('deliveries');" | awk -F'|' '{print $2}' || true)

if ! echo "$cols" | grep -qw payload_json; then
  echo "Adding payload_json column..."
  sqlite3 "$DB" "ALTER TABLE deliveries ADD COLUMN payload_json TEXT;"
  sqlite3 "$DB" "UPDATE deliveries SET payload_json = '{}' WHERE payload_json IS NULL;" || true
else
  echo "payload_json already present; skipping"
fi

if ! echo "$cols" | grep -qw ingested_at; then
  echo "Adding ingested_at column..."
  sqlite3 "$DB" "ALTER TABLE deliveries ADD COLUMN ingested_at TEXT;"
else
  echo "ingested_at already present; skipping"
fi

echo "Backfilling ingested_at for NULLs..."
sqlite3 "$DB" "BEGIN; UPDATE deliveries SET ingested_at = COALESCE(received_at, strftime('%Y-%m-%dT%H:%M:%fZ','now')) WHERE ingested_at IS NULL; COMMIT;" || true

echo "Migration script completed."
