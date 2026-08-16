-- Speed up A2 current-import provenance lookup used once per source message.
-- Without this composite index SQLite can only use the UNIQUE(import_run_id, source_hash)
-- prefix and scans every message_source row in the import run for source_record_key.
CREATE INDEX IF NOT EXISTS idx_message_source_import_record_key
ON message_source(import_run_id, source_record_key)
WHERE source_record_key IS NOT NULL;
