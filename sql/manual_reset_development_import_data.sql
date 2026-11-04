/*
Manual-only recovery for the dedicated SportsFixturesTracker development database.

This script is intentionally NOT a numbered migration and is never called by the
application. The first section is read-only preview. The destructive section is
commented out and has an explicit confirmation guard.

Use only when all of the following are true:
  * The connected database is the dedicated development database SportsFixturesTracker.
  * It was empty before the failed test imports described below.
  * The preview matches the expected failed-import state exactly.
  * A full backup has been created and its successful completion confirmed in SSMS.

Expected state guarded by the execution block:
  * source_snapshot_id 7 is the sole source snapshot.
  * import run 1 is Started and import run 2 is Failed; both use snapshot 7.
  * 14 teams, 7 matches, 14 match results, and 32 match goals exist.

Do NOT use this to remove legitimate development, test, or production records.
The reset cannot determine business ownership of teams or fixtures; its safety
depends on the dedicated-database and exact-state checks above.

Backup before execution (manual SSMS action; no backup is taken by this script):
  1. In Object Explorer, select SportsFixturesTracker.
  2. Choose Tasks > Back Up..., set Backup type to Full, and choose a new .bak path.
  3. Complete the backup and confirm that SSMS reports success before continuing.
*/

USE [SportsFixturesTracker];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

/* ============================================================================
   PREVIEW ONLY - safe to run as-is; performs no INSERT, UPDATE, DELETE, or DDL.
   ============================================================================ */

IF DB_NAME() <> N'SportsFixturesTracker'
    THROW 51000, 'Stop: this preview must run in SportsFixturesTracker.', 1;

SELECT
    DB_NAME() AS current_database,
    CAST(SERVERPROPERTY('ServerName') AS nvarchar(256)) AS connected_server,
    CAST(SERVERPROPERTY('Edition') AS nvarchar(256)) AS sql_server_edition,
    CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)) AS product_version;

SELECT
    source_snapshot_id,
    provider,
    provider_shortcut,
    source_league_id,
    season_start_year,
    matchday_number,
    retrieved_at_utc,
    http_status,
    byte_count,
    sha256
FROM dbo.source_snapshots
ORDER BY source_snapshot_id;

SELECT
    import_run_id,
    source_snapshot_id,
    competition_season_id,
    status,
    is_replay,
    replay_of_import_run_id,
    started_at_utc,
    completed_at_utc,
    failure_phase,
    error_summary
FROM dbo.import_runs
ORDER BY import_run_id;

SELECT N'competitions' AS table_name, COUNT_BIG(*) AS row_count FROM dbo.competitions
UNION ALL
SELECT N'competition_seasons', COUNT_BIG(*) FROM dbo.competition_seasons
UNION ALL
SELECT N'teams', COUNT_BIG(*) FROM dbo.teams
UNION ALL
SELECT N'source_snapshots', COUNT_BIG(*) FROM dbo.source_snapshots
UNION ALL
SELECT N'matches', COUNT_BIG(*) FROM dbo.matches
UNION ALL
SELECT N'match_results', COUNT_BIG(*) FROM dbo.match_results
UNION ALL
SELECT N'match_goals', COUNT_BIG(*) FROM dbo.match_goals
UNION ALL
SELECT N'import_runs', COUNT_BIG(*) FROM dbo.import_runs
UNION ALL
SELECT N'validation_issues', COUNT_BIG(*) FROM dbo.validation_issues
UNION ALL
SELECT N'match_changes', COUNT_BIG(*) FROM dbo.match_changes
UNION ALL
SELECT N'sync_checkpoints', COUNT_BIG(*) FROM dbo.sync_checkpoints
UNION ALL
SELECT N'match_notes', COUNT_BIG(*) FROM dbo.match_notes
ORDER BY table_name;

SELECT
    (SELECT COUNT_BIG(*) FROM dbo.teams) AS teams,
    (SELECT COUNT_BIG(*) FROM dbo.matches) AS matches,
    (SELECT COUNT_BIG(*) FROM dbo.match_results) AS match_results,
    (SELECT COUNT_BIG(*) FROM dbo.match_goals) AS match_goals;

PRINT 'Preview complete. No data was modified.';
PRINT 'Do not execute the reset unless the backup and every expected-state check are confirmed.';
GO

/* ============================================================================
   DESTRUCTIVE EXECUTION - DO NOT RUN AS-IS.

   To execute only after reviewing the preview and completing a full backup:
     1. Remove this opening comment marker and the closing marker at the end.
     2. Leave @confirmation unchanged.
     3. Run this section as one SSMS batch while connected to SportsFixturesTracker.

   The transaction re-checks the exact expected state before any DELETE. Any
   mismatch, error, or remaining application row causes rollback.
   ============================================================================

SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

BEGIN TRY
    BEGIN TRANSACTION;

    /* Operator action required: replace NULL with the exact confirmation phrase. */
    DECLARE @confirmation nvarchar(128) = NULL;

    IF @confirmation IS NULL
       OR @confirmation <> N'RESET-DEDICATED-DEVELOPMENT-DATABASE'
        THROW 51001, 'Stop: destructive-reset confirmation is not present.', 1;

    IF DB_NAME() <> N'SportsFixturesTracker'
        THROW 51002, 'Stop: destructive reset is restricted to SportsFixturesTracker.', 1;

    IF CAST(SERVERPROPERTY('ServerName') AS nvarchar(256)) <> N'CANVASIT'
        THROW 51007, 'Stop: destructive reset is restricted to server CANVASIT.', 1;

    IF (SELECT COUNT_BIG(*) FROM dbo.source_snapshots) <> 1
       OR NOT EXISTS
       (
           SELECT 1
           FROM dbo.source_snapshots
           WHERE source_snapshot_id = 7
       )
       OR EXISTS
       (
           SELECT 1
           FROM dbo.source_snapshots
           WHERE source_snapshot_id <> 7
              OR provider <> N'OpenLigaDB'
              OR provider_shortcut <> N'ucl'
              OR source_league_id <> 4946
              OR season_start_year <> 2026
       )
        THROW 51003, 'Stop: source-snapshot state differs from the reviewed reset scope.', 1;

    IF (SELECT COUNT_BIG(*) FROM dbo.import_runs) <> 2
       OR NOT EXISTS
       (
           SELECT 1
           FROM dbo.import_runs
           WHERE import_run_id = 1
             AND source_snapshot_id = 7
             AND status = 'Started'
       )
       OR NOT EXISTS
       (
           SELECT 1
           FROM dbo.import_runs
           WHERE import_run_id = 2
             AND source_snapshot_id = 7
             AND status = 'Failed'
       )
       OR EXISTS
       (
           SELECT 1
           FROM dbo.import_runs
           WHERE import_run_id NOT IN (1, 2)
              OR source_snapshot_id <> 7
              OR replay_of_import_run_id IS NOT NULL
       )
        THROW 51004, 'Stop: import-run state differs from the reviewed reset scope.', 1;

    IF (SELECT COUNT_BIG(*) FROM dbo.competitions) <> 1
       OR (SELECT COUNT_BIG(*) FROM dbo.competition_seasons) <> 1
       OR (SELECT COUNT_BIG(*) FROM dbo.teams) <> 14
       OR (SELECT COUNT_BIG(*) FROM dbo.matches) <> 7
       OR (SELECT COUNT_BIG(*) FROM dbo.match_results) <> 14
       OR (SELECT COUNT_BIG(*) FROM dbo.match_goals) <> 32
       OR EXISTS (SELECT 1 FROM dbo.match_notes)
       OR EXISTS
       (
           SELECT 1
           FROM dbo.competitions
           WHERE provider <> N'OpenLigaDB'
              OR provider_shortcut <> N'ucl'
       )
       OR EXISTS (SELECT 1 FROM dbo.matches WHERE provider <> N'OpenLigaDB')
       OR EXISTS (SELECT 1 FROM dbo.teams WHERE provider <> N'OpenLigaDB')
       OR EXISTS (SELECT 1 FROM dbo.match_results WHERE provider <> N'OpenLigaDB')
       OR EXISTS (SELECT 1 FROM dbo.match_goals WHERE provider <> N'OpenLigaDB')
        THROW 51005, 'Stop: application data is not the reviewed dedicated-import state.', 1;

    DECLARE @target_runs TABLE (import_run_id bigint NOT NULL PRIMARY KEY);
    DECLARE @target_matches TABLE (match_id bigint NOT NULL PRIMARY KEY);

    INSERT @target_runs (import_run_id)
    SELECT import_run_id
    FROM dbo.import_runs
    WHERE import_run_id IN (1, 2);

    INSERT @target_matches (match_id)
    SELECT match_id
    FROM dbo.matches;

    /* Delete foreign-key dependents first. Local notes are blocked above rather
       than deleted, because they can be user-authored development data. */
    DELETE mc
    FROM dbo.match_changes AS mc
    WHERE mc.source_snapshot_id = 7
       OR EXISTS
       (
           SELECT 1
           FROM @target_runs AS tr
           WHERE tr.import_run_id = mc.import_run_id
       )
       OR EXISTS
       (
           SELECT 1
           FROM @target_matches AS tm
           WHERE tm.match_id = mc.match_id
       );

    DELETE vi
    FROM dbo.validation_issues AS vi
    WHERE vi.source_snapshot_id = 7
       OR EXISTS
       (
           SELECT 1
           FROM @target_runs AS tr
           WHERE tr.import_run_id = vi.import_run_id
       );

    DELETE sc
    FROM dbo.sync_checkpoints AS sc
    WHERE sc.last_successful_snapshot_id = 7
       OR EXISTS
       (
           SELECT 1
           FROM @target_runs AS tr
           WHERE tr.import_run_id = sc.last_successful_import_run_id
       );

    DELETE mg
    FROM dbo.match_goals AS mg
    INNER JOIN @target_matches AS tm ON tm.match_id = mg.match_id;

    DELETE mr
    FROM dbo.match_results AS mr
    INNER JOIN @target_matches AS tm ON tm.match_id = mr.match_id;

    DELETE m
    FROM dbo.matches AS m
    INNER JOIN @target_matches AS tm ON tm.match_id = m.match_id;

    DELETE ir
    FROM dbo.import_runs AS ir
    INNER JOIN @target_runs AS tr ON tr.import_run_id = ir.import_run_id;

    DELETE FROM dbo.source_snapshots WHERE source_snapshot_id = 7;
    DELETE FROM dbo.teams;
    DELETE FROM dbo.competition_seasons;
    DELETE FROM dbo.competitions;

    IF EXISTS (SELECT 1 FROM dbo.competitions)
       OR EXISTS (SELECT 1 FROM dbo.competition_seasons)
       OR EXISTS (SELECT 1 FROM dbo.teams)
       OR EXISTS (SELECT 1 FROM dbo.source_snapshots)
       OR EXISTS (SELECT 1 FROM dbo.matches)
       OR EXISTS (SELECT 1 FROM dbo.match_results)
       OR EXISTS (SELECT 1 FROM dbo.match_goals)
       OR EXISTS (SELECT 1 FROM dbo.import_runs)
       OR EXISTS (SELECT 1 FROM dbo.validation_issues)
       OR EXISTS (SELECT 1 FROM dbo.match_changes)
       OR EXISTS (SELECT 1 FROM dbo.sync_checkpoints)
       OR EXISTS (SELECT 1 FROM dbo.match_notes)
        THROW 51006, 'Stop: application tables are not empty; the reset was rolled back.', 1;

    COMMIT TRANSACTION;
    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    PRINT 'Development import data reset committed. Verify the preview queries now return zero rows.';
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    THROW;
END CATCH;
*/
