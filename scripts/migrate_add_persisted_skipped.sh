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

echo "Checking if columns already exist..."
exists=$(sqlite3 "$DB_PATH" "PRAGMA table_info('deliveries');" | grep -E "persisted_count|skipped_count" || true)
if [ -n "$exists" ]; then
  echo "persisted_count or skipped_count already present; nothing to do."
  exit 0
fi

echo "Adding columns persisted_count and skipped_count (default 0)..."
sqlite3 "$DB_PATH" <<'SQL'
BEGIN;
ALTER TABLE deliveries ADD COLUMN persisted_count INTEGER DEFAULT 0;
ALTER TABLE deliveries ADD COLUMN skipped_count INTEGER DEFAULT 0;
COMMIT;
SQL

echo "Done. New table schema:"
sqlite3 "$DB_PATH" "PRAGMA table_info('deliveries');"
