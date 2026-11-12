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

ALTER ROLE sports_tracker_api NOLOGIN;
ALTER ROLE sports_tracker_sync NOLOGIN;
ALTER ROLE sports_tracker_migrator NOLOGIN;

-- Restrict only the application roles created above. Do not revoke privileges
-- from PUBLIC across the whole schema because provider-managed objects may share it.
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public
    FROM sports_tracker_api, sports_tracker_sync, sports_tracker_migrator;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public
    FROM sports_tracker_api, sports_tracker_sync, sports_tracker_migrator;
REVOKE ALL PRIVILEGES ON SCHEMA public
    FROM sports_tracker_api, sports_tracker_sync, sports_tracker_migrator;

GRANT USAGE ON SCHEMA public TO sports_tracker_api, sports_tracker_sync, sports_tracker_migrator;

-- Public application queries are read-only. Internal tables and local notes are absent.
GRANT SELECT ON TABLE
    public.competitions,
    public.competition_seasons,
    public.teams,
    public.source_snapshots,
    public.matches,
    public.match_results,
    public.match_goals,
    public.match_changes,
    public.sync_checkpoints
TO sports_tracker_api;

-- Synchronization needs current-row/provenance DML and lease replacement, but no
-- local-note, migration-ledger, DDL, TRUNCATE, or destructive domain-row privilege.
GRANT SELECT, INSERT, UPDATE ON TABLE
    public.competitions,
    public.competition_seasons,
    public.teams,
    public.source_snapshots,
    public.matches,
    public.match_results,
    public.match_goals,
    public.import_runs,
    public.validation_issues,
    public.match_changes,
    public.sync_checkpoints
TO sports_tracker_sync;
GRANT SELECT, INSERT, DELETE ON TABLE public.sync_leases TO sports_tracker_sync;
GRANT USAGE, SELECT ON SEQUENCE
    public.competitions_competition_id_seq,
    public.competition_seasons_competition_season_id_seq,
    public.teams_team_id_seq,
    public.source_snapshots_source_snapshot_id_seq,
    public.matches_match_id_seq,
    public.match_results_match_result_id_seq,
    public.match_goals_match_goal_id_seq,
    public.import_runs_import_run_id_seq,
    public.validation_issues_validation_issue_id_seq,
    public.match_changes_match_change_id_seq,
    public.sync_checkpoints_sync_checkpoint_id_seq
TO sports_tracker_sync;

-- Migration is a controlled owner-operated operation and may insert explicit IDs.
GRANT SELECT, INSERT, UPDATE ON TABLE
    public.competitions,
    public.competition_seasons,
    public.teams,
    public.source_snapshots,
    public.matches,
    public.match_results,
    public.match_goals,
    public.import_runs,
    public.validation_issues,
    public.match_changes,
    public.sync_checkpoints,
    public.match_notes
TO sports_tracker_migrator;
GRANT USAGE, SELECT, UPDATE ON SEQUENCE
    public.competitions_competition_id_seq,
    public.competition_seasons_competition_season_id_seq,
    public.teams_team_id_seq,
    public.source_snapshots_source_snapshot_id_seq,
    public.matches_match_id_seq,
    public.match_results_match_result_id_seq,
    public.match_goals_match_goal_id_seq,
    public.import_runs_import_run_id_seq,
    public.validation_issues_validation_issue_id_seq,
    public.match_changes_match_change_id_seq,
    public.sync_checkpoints_sync_checkpoint_id_seq,
    public.match_notes_match_note_id_seq
TO sports_tracker_migrator;

-- Future tables and sequences require an explicit privilege review; do not use
-- broad default grants that would expose internal objects automatically.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON TABLES FROM sports_tracker_api, sports_tracker_sync, sports_tracker_migrator;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM sports_tracker_api, sports_tracker_sync, sports_tracker_migrator;

COMMIT;
