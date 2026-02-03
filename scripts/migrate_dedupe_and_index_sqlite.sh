set -euo pipefail

DB="data/deliveries.db"
BACKUP_DIR="${HOME}/oo_backup_over_under"
TIMESTAMP=$(date +%Y%m%d%H%M%S)

if [ ! -f "$DB" ]; then
  echo "ERROR: DB not found at $DB"
  exit 1
fi

mkdir -p "$BACKUP_DIR"
cp "$DB" "$BACKUP_DIR/deliveries.db.${TIMESTAMP}"
echo "Backed up $DB -> $BACKUP_DIR/deliveries.db.${TIMESTAMP}"

echo
echo "STEP 1: Show duplicate match_id counts (if any):"
sqlite3 "$DB" <<'SQL'
.mode column
.headers on
SELECT match_id, COUNT(*) AS cnt
FROM deliveries
GROUP BY match_id
HAVING cnt > 1
ORDER BY cnt DESC;
SQL

echo
echo "STEP 2: Dry-run: list rows that WOULD be deleted (older rows), review output above."
sqlite3 "$DB" <<'SQL'
.mode column
.headers on
SELECT d.rowid AS id, d.match_id, d.received_at
FROM deliveries d
JOIN (
  SELECT match_id, MAX(received_at) AS keep_at
  FROM deliveries
  GROUP BY match_id
  HAVING COUNT(*) > 1
) k ON d.match_id = k.match_id
WHERE d.received_at < k.keep_at
ORDER BY d.match_id, d.received_at;
SQL

echo
read -p "If the dry-run looks good, type YES to apply dedupe and add unique index: " CONFIRM
if [ "$CONFIRM" != "YES" ]; then
  echo "Aborting. No changes made."
  exit 0
fi

echo "Applying dedupe: deleting older rows (keeps newest received_at)..."
sqlite3 "$DB" <<'SQL'
BEGIN;
DELETE FROM deliveries
WHERE rowid IN (
  SELECT d.rowid FROM deliveries d
  JOIN (
    SELECT match_id, MAX(received_at) AS keep_received_at FROM deliveries GROUP BY match_id HAVING COUNT(*) > 1
  ) k ON d.match_id = k.match_id
  WHERE d.received_at < k.keep_received_at
);
COMMIT;
SQL
echo "Dedupe applied."

echo "Creating unique index on match_id (if not exists)..."
sqlite3 "$DB" "CREATE UNIQUE INDEX IF NOT EXISTS deliveries_match_id_uix ON deliveries(match_id);"
echo "Unique index ensured."

echo
echo "FINAL CHECK: show duplicate counts again (should be none):"
sqlite3 "$DB" <<'SQL'
.headers on
.mode column
SELECT match_id, COUNT(*) AS cnt
FROM deliveries
GROUP BY match_id
HAVING cnt > 1
ORDER BY cnt DESC;
SQL

echo "Done. Backup is at: $BACKUP_DIR/deliveries.db.${TIMESTAMP}"
