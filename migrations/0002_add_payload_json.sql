-- Add payload_json and ingested_at columns for older DB snapshots
ALTER TABLE deliveries ADD COLUMN payload_json TEXT;
UPDATE deliveries SET payload_json = '{}' WHERE payload_json IS NULL;

ALTER TABLE deliveries ADD COLUMN ingested_at TEXT;
UPDATE deliveries SET ingested_at = COALESCE(received_at, strftime('%Y-%m-%dT%H:%M:%fZ','now')) WHERE ingested_at IS NULL;
