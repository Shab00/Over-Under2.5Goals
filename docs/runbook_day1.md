# Day‑1: Production readiness — migrate deliveries DB, verify, and rollback

## Summary
This runbook describes how to run the interactive dedupe + index migration, verify end-to-end, and rollback if needed.

## Preconditions
- Ensure you have a shell on the target host with repo checked out.
- Ensure Python/uvicorn environment as used in production/staging.
- Have SSH/access to the staging/production host and necessary privileges.

## Backup (always do this first)
Runs on the host where `data/deliveries.db` lives.

```bash
mkdir -p ~/oo_backup_over_under
timestamp=$(date -u +"%Y%m%d%H%M%S")
cp data/deliveries.db ~/oo_backup_over_under/deliveries.db.$timestamp
echo "Backup created: ~/oo_backup_over_under/deliveries.db.$timestamp"
```

## Run the migration (interactive)
```bash
chmod +x scripts/migrate_dedupe_and_index_sqlite.sh
./scripts/migrate_dedupe_and_index_sqlite.sh
# Inspect the dry-run output. Type YES to apply changes.
```

## Verify migration completed
```bash
# No duplicate match_ids
sqlite3 data/deliveries.db "SELECT match_id, COUNT(*) AS cnt FROM deliveries GROUP BY match_id HAVING cnt>1;"

# Confirm index exists
sqlite3 data/deliveries.db "PRAGMA index_list('deliveries');"
sqlite3 data/deliveries.db "SELECT name, sql FROM sqlite_master WHERE type='index' AND name='deliveries_match_id_uix';"
```

## Restart the API (example using uvicorn)
```bash
pkill -f uvicorn || true
uvicorn src.api.main:APP --reload --host 127.0.0.1 --port 8000 &
# or use your host's process manager (systemd/docker/etc)
```

## Run smoke test
```bash
# Run sender in TEST_MODE and skip sending telegram to avoid real messages
SKIP_TELEGRAM=1 TEST_MODE=1 DELIVERIES_DB="deliveries.db" python scripts/send_telegram_digest.py --limit 2
# Verify summary
sqlite3 deliveries.db "SELECT id, total_sent, persisted_count, skipped_count, ingest_response_json, sent_at FROM deliveries_summary ORDER BY id DESC LIMIT 1;"
# Verify persisted rows
sqlite3 data/deliveries.db "SELECT id, match_id, received_at FROM deliveries ORDER BY id DESC LIMIT 10;"
```

## Rollback procedure (if something goes wrong)
1. Stop API (if necessary)
```bash
pkill -f uvicorn || true
```

2. Restore backup (replace <timestamp> with the one created earlier)
```bash
cp ~/oo_backup_over_under/deliveries.db.<timestamp> data/deliveries.db
```

3. Restart API
```bash
uvicorn src.api.main:APP --reload --host 127.0.0.1 --port 8000 &
```

4. Re-run smoke test (see above) and validate.

## Notes & follow-ups
- Add server-side idempotency: prefer `INSERT OR IGNORE` or catch IntegrityError and return success to caller.
- Consider dropping redundant indexes after monitoring.
- Run this on a staging host before production. Always backup production DB before running the script.
