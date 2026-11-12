-- Run as the Neon database owner after 001_initial_schema.sql.
-- Create LOGIN roles through the provider's secret-management workflow, then
-- grant them membership in these NOLOGIN groups. No passwords belong in Git.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sports_tracker_api') THEN
        CREATE ROLE sports_tracker_api NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sports_tracker_sync') THEN
        CREATE ROLE sports_tracker_sync NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sports_tracker_migrator') THEN
        CREATE ROLE sports_tracker_migrator NOLOGIN;
    END IF;
END
$$;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO sports_tracker_api, sports_tracker_sync, sports_tracker_migrator;

-- Public application queries are read-only. Note writes are deliberately absent.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sports_tracker_api;

-- Synchronization needs row-level reads and inserts/updates, but no destructive DDL
-- or DELETE/TRUNCATE privileges.
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO sports_tracker_sync;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sports_tracker_sync;

-- Migration is a controlled owner-operated operation and may insert explicit IDs.
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO sports_tracker_migrator;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO sports_tracker_migrator;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO sports_tracker_api;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE ON TABLES TO sports_tracker_sync;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE ON TABLES TO sports_tracker_migrator;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO sports_tracker_sync;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO sports_tracker_migrator;

COMMIT;
