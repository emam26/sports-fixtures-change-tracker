-- Apply after 001_initial_schema.sql and 002_roles.sql as the database owner.
-- Additive migration: existing source_snapshot IDs, records and checkpoints are unchanged.
BEGIN;

CREATE TABLE IF NOT EXISTS public.raw_snapshot_blobs (
    snapshot_key text PRIMARY KEY,
    response_bytes bytea NOT NULL,
    metadata_bytes bytea NOT NULL,
    response_sha256 text NOT NULL,
    metadata_sha256 text NOT NULL,
    archived_at_utc timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (snapshot_key LIKE 'postgresql/sports-fixtures/raw/%'),
    CHECK (response_sha256 = encode(sha256(response_bytes), 'hex')),
    CHECK (metadata_sha256 = encode(sha256(metadata_bytes), 'hex'))
);

-- Raw captures are private, even when the API remains available through Render.
REVOKE ALL ON TABLE public.raw_snapshot_blobs
FROM PUBLIC, sports_tracker_api, sports_tracker_sync, sports_tracker_migrator;

GRANT SELECT, INSERT ON TABLE public.raw_snapshot_blobs
TO sports_tracker_sync, sports_tracker_migrator;

INSERT INTO public.schema_migrations (version)
VALUES ('003_raw_snapshot_archive')
ON CONFLICT (version) DO NOTHING;

COMMIT;
