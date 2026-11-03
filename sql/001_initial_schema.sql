/*
    Sports Fixtures & Change Tracker - Stage 2 initial schema

    Execute manually in SSMS against the existing SportsFixturesTracker database.
    This script creates missing dbo objects only. It never drops databases, tables,
    constraints, indexes, logins, or existing data, and it grants no permissions.

    Raw OpenLigaDB response bytes remain on disk under data/raw/. The database
    stores snapshot metadata and paths so later imports can retain provenance.
*/

USE [SportsFixturesTracker];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.competitions', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.competitions
        (
            competition_id bigint IDENTITY(1, 1) NOT NULL
                CONSTRAINT PK_competitions PRIMARY KEY,
            provider nvarchar(50) NOT NULL,
            provider_shortcut nvarchar(50) NOT NULL,
            competition_name nvarchar(200) NOT NULL,
            is_active bit NOT NULL
                CONSTRAINT DF_competitions_is_active DEFAULT (1),
            created_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_competitions_created_at_utc DEFAULT (SYSUTCDATETIME()),
            updated_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_competitions_updated_at_utc DEFAULT (SYSUTCDATETIME()),
            CONSTRAINT UQ_competitions_provider_shortcut
                UNIQUE (provider, provider_shortcut),
            CONSTRAINT CK_competitions_provider_not_blank
                CHECK (LEN(LTRIM(RTRIM(provider))) > 0),
            CONSTRAINT CK_competitions_shortcut_not_blank
                CHECK (LEN(LTRIM(RTRIM(provider_shortcut))) > 0),
            CONSTRAINT CK_competitions_name_not_blank
                CHECK (LEN(LTRIM(RTRIM(competition_name))) > 0)
        );
    END;

    IF OBJECT_ID(N'dbo.competition_seasons', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.competition_seasons
        (
            competition_season_id bigint IDENTITY(1, 1) NOT NULL
                CONSTRAINT PK_competition_seasons PRIMARY KEY,
            competition_id bigint NOT NULL,
            source_league_id int NOT NULL,
            season_start_year smallint NOT NULL,
            season_label nvarchar(20) NULL,
            created_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_competition_seasons_created_at_utc DEFAULT (SYSUTCDATETIME()),
            CONSTRAINT FK_competition_seasons_competitions
                FOREIGN KEY (competition_id)
                REFERENCES dbo.competitions (competition_id),
            CONSTRAINT UQ_competition_seasons_identity
                UNIQUE (competition_id, source_league_id, season_start_year),
            CONSTRAINT CK_competition_seasons_league_id_positive
                CHECK (source_league_id > 0),
            CONSTRAINT CK_competition_seasons_year_range
                CHECK (season_start_year BETWEEN 1900 AND 2200)
        );
    END;

    IF OBJECT_ID(N'dbo.teams', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.teams
        (
            team_id bigint IDENTITY(1, 1) NOT NULL
                CONSTRAINT PK_teams PRIMARY KEY,
            provider nvarchar(50) NOT NULL,
            provider_team_id bigint NOT NULL,
            team_name nvarchar(200) NOT NULL,
            short_name nvarchar(100) NULL,
            tla nvarchar(20) NULL,
            team_group_name nvarchar(200) NULL,
            team_icon_url nvarchar(2048) NULL,
            wikidata_id nvarchar(100) NULL,
            created_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_teams_created_at_utc DEFAULT (SYSUTCDATETIME()),
            updated_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_teams_updated_at_utc DEFAULT (SYSUTCDATETIME()),
            CONSTRAINT UQ_teams_provider_team
                UNIQUE (provider, provider_team_id),
            CONSTRAINT CK_teams_provider_not_blank
                CHECK (LEN(LTRIM(RTRIM(provider))) > 0),
            CONSTRAINT CK_teams_provider_id_positive
                CHECK (provider_team_id > 0),
            CONSTRAINT CK_teams_name_not_blank
                CHECK (LEN(LTRIM(RTRIM(team_name))) > 0)
        );
    END;

    IF OBJECT_ID(N'dbo.source_snapshots', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.source_snapshots
        (
            source_snapshot_id bigint IDENTITY(1, 1) NOT NULL
                CONSTRAINT PK_source_snapshots PRIMARY KEY,
            provider nvarchar(50) NOT NULL,
            provider_shortcut nvarchar(50) NOT NULL,
            source_league_id int NOT NULL,
            season_start_year smallint NOT NULL,
            matchday_number int NULL,
            competition_stage nvarchar(100) NULL,
            source_url nvarchar(2048) NOT NULL,
            retrieved_at_utc datetime2(7) NOT NULL,
            http_status smallint NOT NULL,
            content_type nvarchar(255) NULL,
            byte_count bigint NOT NULL,
            sha256 char(64) NOT NULL,
            -- The provider/local_directory unique key stays below SQL Server's
            -- 1,700-byte nonclustered index-key limit: 100 + 1,500 bytes.
            local_directory nvarchar(750) NOT NULL,
            response_path nvarchar(2048) NOT NULL,
            metadata_path nvarchar(2048) NOT NULL,
            created_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_source_snapshots_created_at_utc DEFAULT (SYSUTCDATETIME()),
            CONSTRAINT UQ_source_snapshots_local_directory
                UNIQUE (provider, local_directory),
            CONSTRAINT CK_source_snapshots_provider_not_blank
                CHECK (LEN(LTRIM(RTRIM(provider))) > 0),
            CONSTRAINT CK_source_snapshots_shortcut_not_blank
                CHECK (LEN(LTRIM(RTRIM(provider_shortcut))) > 0),
            CONSTRAINT CK_source_snapshots_league_id_positive
                CHECK (source_league_id > 0),
            CONSTRAINT CK_source_snapshots_year_range
                CHECK (season_start_year BETWEEN 1900 AND 2200),
            CONSTRAINT CK_source_snapshots_matchday_positive
                CHECK (matchday_number IS NULL OR matchday_number > 0),
            CONSTRAINT CK_source_snapshots_http_status
                CHECK (http_status BETWEEN 100 AND 599),
            CONSTRAINT CK_source_snapshots_byte_count
                CHECK (byte_count >= 0),
            CONSTRAINT CK_source_snapshots_sha256_length
                CHECK (LEN(sha256) = 64)
        );
    END;

    IF OBJECT_ID(N'dbo.matches', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.matches
        (
            match_id bigint IDENTITY(1, 1) NOT NULL
                CONSTRAINT PK_matches PRIMARY KEY,
            competition_season_id bigint NOT NULL,
            provider nvarchar(50) NOT NULL,
            provider_match_id bigint NOT NULL,
            home_team_id bigint NOT NULL,
            away_team_id bigint NOT NULL,
            matchday_number int NULL,
            competition_stage nvarchar(100) NULL,
            source_group_id bigint NULL,
            source_group_order_id int NULL,
            source_group_name nvarchar(200) NULL,
            kickoff_utc datetime2(7) NULL,
            source_match_is_finished bit NOT NULL,
            source_last_update_utc datetime2(7) NULL,
            source_last_update_raw nvarchar(64) NULL,
            source_time_zone_id nvarchar(128) NULL,
            location nvarchar(256) NULL,
            created_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_matches_created_at_utc DEFAULT (SYSUTCDATETIME()),
            updated_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_matches_updated_at_utc DEFAULT (SYSUTCDATETIME()),
            CONSTRAINT FK_matches_competition_seasons
                FOREIGN KEY (competition_season_id)
                REFERENCES dbo.competition_seasons (competition_season_id),
            CONSTRAINT FK_matches_home_team
                FOREIGN KEY (home_team_id)
                REFERENCES dbo.teams (team_id),
            CONSTRAINT FK_matches_away_team
                FOREIGN KEY (away_team_id)
                REFERENCES dbo.teams (team_id),
            CONSTRAINT UQ_matches_provider_match
                UNIQUE (provider, provider_match_id),
            CONSTRAINT CK_matches_provider_not_blank
                CHECK (LEN(LTRIM(RTRIM(provider))) > 0),
            CONSTRAINT CK_matches_provider_id_positive
                CHECK (provider_match_id > 0),
            CONSTRAINT CK_matches_distinct_teams
                CHECK (home_team_id <> away_team_id),
            CONSTRAINT CK_matches_matchday_positive
                CHECK (matchday_number IS NULL OR matchday_number > 0),
            CONSTRAINT CK_matches_source_group_order_positive
                CHECK (source_group_order_id IS NULL OR source_group_order_id > 0)
        );
    END;

    IF OBJECT_ID(N'dbo.match_results', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.match_results
        (
            match_result_id bigint IDENTITY(1, 1) NOT NULL
                CONSTRAINT PK_match_results PRIMARY KEY,
            match_id bigint NOT NULL,
            provider nvarchar(50) NOT NULL,
            provider_result_id bigint NOT NULL,
            result_type_id int NULL,
            result_type_kind nvarchar(100) NOT NULL,
            result_order_id int NULL,
            result_name nvarchar(200) NULL,
            result_description nvarchar(500) NULL,
            points_team1 int NULL,
            points_team2 int NULL,
            created_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_match_results_created_at_utc DEFAULT (SYSUTCDATETIME()),
            CONSTRAINT FK_match_results_matches
                FOREIGN KEY (match_id)
                REFERENCES dbo.matches (match_id),
            CONSTRAINT UQ_match_results_match_result
                UNIQUE (match_id, provider_result_id),
            CONSTRAINT UQ_match_results_match_type
                UNIQUE (match_id, result_type_kind),
            CONSTRAINT CK_match_results_provider_not_blank
                CHECK (LEN(LTRIM(RTRIM(provider))) > 0),
            CONSTRAINT CK_match_results_provider_id_positive
                CHECK (provider_result_id > 0),
            CONSTRAINT CK_match_results_type_not_blank
                CHECK (LEN(LTRIM(RTRIM(result_type_kind))) > 0),
            CONSTRAINT CK_match_results_score_pair
                CHECK (
                    (points_team1 IS NULL AND points_team2 IS NULL)
                    OR (points_team1 IS NOT NULL AND points_team2 IS NOT NULL)
                ),
            CONSTRAINT CK_match_results_scores_nonnegative
                CHECK (
                    (points_team1 IS NULL OR points_team1 >= 0)
                    AND (points_team2 IS NULL OR points_team2 >= 0)
                )
        );
    END;

    /*
        The saved Stage 1 responses contain a stable goals collection with
        goalID, scoreTeam1/2, matchMinute, goalGetterID/name, scoringTeamId,
        penalty/own-goal/overtime flags, and comment. Optional text fields stay
        nullable because the provider can omit them.
    */
    IF OBJECT_ID(N'dbo.match_goals', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.match_goals
        (
            match_goal_id bigint IDENTITY(1, 1) NOT NULL
                CONSTRAINT PK_match_goals PRIMARY KEY,
            match_id bigint NOT NULL,
            provider nvarchar(50) NOT NULL,
            provider_goal_id bigint NOT NULL,
            score_team1 int NULL,
            score_team2 int NULL,
            match_minute int NULL,
            goal_getter_provider_id bigint NULL,
            goal_getter_name nvarchar(200) NULL,
            scoring_team_id bigint NULL,
            is_penalty bit NULL,
            is_own_goal bit NULL,
            is_overtime bit NULL,
            comment nvarchar(1000) NULL,
            created_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_match_goals_created_at_utc DEFAULT (SYSUTCDATETIME()),
            CONSTRAINT FK_match_goals_matches
                FOREIGN KEY (match_id)
                REFERENCES dbo.matches (match_id),
            CONSTRAINT FK_match_goals_scoring_team
                FOREIGN KEY (scoring_team_id)
                REFERENCES dbo.teams (team_id),
            CONSTRAINT UQ_match_goals_match_goal
                UNIQUE (match_id, provider_goal_id),
            CONSTRAINT CK_match_goals_provider_not_blank
                CHECK (LEN(LTRIM(RTRIM(provider))) > 0),
            CONSTRAINT CK_match_goals_provider_id_positive
                CHECK (provider_goal_id > 0),
            CONSTRAINT CK_match_goals_scores_nonnegative
                CHECK (
                    (score_team1 IS NULL OR score_team1 >= 0)
                    AND (score_team2 IS NULL OR score_team2 >= 0)
                ),
            CONSTRAINT CK_match_goals_minute_nonnegative
                CHECK (match_minute IS NULL OR match_minute >= 0)
        );
    END;

    IF OBJECT_ID(N'dbo.import_runs', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.import_runs
        (
            import_run_id bigint IDENTITY(1, 1) NOT NULL
                CONSTRAINT PK_import_runs PRIMARY KEY,
            provider nvarchar(50) NOT NULL,
            competition_season_id bigint NULL,
            source_snapshot_id bigint NULL,
            matchday_number int NULL,
            competition_stage nvarchar(100) NULL,
            requested_url nvarchar(2048) NULL,
            started_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_import_runs_started_at_utc DEFAULT (SYSUTCDATETIME()),
            completed_at_utc datetime2(7) NULL,
            status varchar(20) NOT NULL
                CONSTRAINT DF_import_runs_status DEFAULT ('Started'),
            is_replay bit NOT NULL
                CONSTRAINT DF_import_runs_is_replay DEFAULT (0),
            replay_of_import_run_id bigint NULL,
            matches_seen int NOT NULL
                CONSTRAINT DF_import_runs_matches_seen DEFAULT (0),
            matches_inserted int NOT NULL
                CONSTRAINT DF_import_runs_matches_inserted DEFAULT (0),
            matches_updated int NOT NULL
                CONSTRAINT DF_import_runs_matches_updated DEFAULT (0),
            matches_unchanged int NOT NULL
                CONSTRAINT DF_import_runs_matches_unchanged DEFAULT (0),
            matches_rejected int NOT NULL
                CONSTRAINT DF_import_runs_matches_rejected DEFAULT (0),
            results_seen int NOT NULL
                CONSTRAINT DF_import_runs_results_seen DEFAULT (0),
            validation_issue_count int NOT NULL
                CONSTRAINT DF_import_runs_validation_issue_count DEFAULT (0),
            failure_phase nvarchar(100) NULL,
            error_summary nvarchar(4000) NULL,
            created_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_import_runs_created_at_utc DEFAULT (SYSUTCDATETIME()),
            CONSTRAINT FK_import_runs_competition_seasons
                FOREIGN KEY (competition_season_id)
                REFERENCES dbo.competition_seasons (competition_season_id),
            CONSTRAINT FK_import_runs_source_snapshots
                FOREIGN KEY (source_snapshot_id)
                REFERENCES dbo.source_snapshots (source_snapshot_id),
            CONSTRAINT FK_import_runs_replay_parent
                FOREIGN KEY (replay_of_import_run_id)
                REFERENCES dbo.import_runs (import_run_id),
            CONSTRAINT CK_import_runs_provider_not_blank
                CHECK (LEN(LTRIM(RTRIM(provider))) > 0),
            CONSTRAINT CK_import_runs_matchday_positive
                CHECK (matchday_number IS NULL OR matchday_number > 0),
            CONSTRAINT CK_import_runs_status
                CHECK (status IN ('Started', 'Succeeded', 'Failed', 'RolledBack', 'Skipped')),
            CONSTRAINT CK_import_runs_completed_after_started
                CHECK (completed_at_utc IS NULL OR completed_at_utc >= started_at_utc),
            CONSTRAINT CK_import_runs_counts_nonnegative
                CHECK (
                    matches_seen >= 0
                    AND matches_inserted >= 0
                    AND matches_updated >= 0
                    AND matches_unchanged >= 0
                    AND matches_rejected >= 0
                    AND results_seen >= 0
                    AND validation_issue_count >= 0
                ),
            CONSTRAINT CK_import_runs_replay_parent
                CHECK (
                    (is_replay = 0 AND replay_of_import_run_id IS NULL)
                    OR (is_replay = 1 AND replay_of_import_run_id IS NOT NULL)
                )
        );
    END;

    IF OBJECT_ID(N'dbo.validation_issues', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.validation_issues
        (
            validation_issue_id bigint IDENTITY(1, 1) NOT NULL
                CONSTRAINT PK_validation_issues PRIMARY KEY,
            import_run_id bigint NULL,
            source_snapshot_id bigint NULL,
            provider nvarchar(50) NOT NULL,
            source_record_type nvarchar(100) NULL,
            source_record_id nvarchar(100) NULL,
            field_name nvarchar(128) NULL,
            issue_code nvarchar(100) NOT NULL,
            severity varchar(20) NOT NULL,
            issue_message nvarchar(2000) NOT NULL,
            source_value nvarchar(4000) NULL,
            is_resolved bit NOT NULL
                CONSTRAINT DF_validation_issues_is_resolved DEFAULT (0),
            created_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_validation_issues_created_at_utc DEFAULT (SYSUTCDATETIME()),
            CONSTRAINT FK_validation_issues_import_runs
                FOREIGN KEY (import_run_id)
                REFERENCES dbo.import_runs (import_run_id),
            CONSTRAINT FK_validation_issues_source_snapshots
                FOREIGN KEY (source_snapshot_id)
                REFERENCES dbo.source_snapshots (source_snapshot_id),
            CONSTRAINT CK_validation_issues_provider_not_blank
                CHECK (LEN(LTRIM(RTRIM(provider))) > 0),
            CONSTRAINT CK_validation_issues_code_not_blank
                CHECK (LEN(LTRIM(RTRIM(issue_code))) > 0),
            CONSTRAINT CK_validation_issues_message_not_blank
                CHECK (LEN(LTRIM(RTRIM(issue_message))) > 0),
            CONSTRAINT CK_validation_issues_severity
                CHECK (severity IN ('Info', 'Warning', 'Error'))
        );
    END;

    IF OBJECT_ID(N'dbo.match_changes', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.match_changes
        (
            match_change_id bigint IDENTITY(1, 1) NOT NULL
                CONSTRAINT PK_match_changes PRIMARY KEY,
            match_id bigint NOT NULL,
            import_run_id bigint NOT NULL,
            source_snapshot_id bigint NOT NULL,
            field_name nvarchar(128) NOT NULL,
            change_kind varchar(20) NOT NULL,
            old_value nvarchar(max) NULL,
            new_value nvarchar(max) NULL,
            observed_at_utc datetime2(7) NOT NULL,
            source_last_update_utc datetime2(7) NULL,
            created_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_match_changes_created_at_utc DEFAULT (SYSUTCDATETIME()),
            CONSTRAINT FK_match_changes_matches
                FOREIGN KEY (match_id)
                REFERENCES dbo.matches (match_id),
            CONSTRAINT FK_match_changes_import_runs
                FOREIGN KEY (import_run_id)
                REFERENCES dbo.import_runs (import_run_id),
            CONSTRAINT FK_match_changes_source_snapshots
                FOREIGN KEY (source_snapshot_id)
                REFERENCES dbo.source_snapshots (source_snapshot_id),
            CONSTRAINT UQ_match_changes_snapshot_match_field
                UNIQUE (source_snapshot_id, match_id, field_name, change_kind),
            CONSTRAINT CK_match_changes_field_not_blank
                CHECK (LEN(LTRIM(RTRIM(field_name))) > 0),
            CONSTRAINT CK_match_changes_kind
                CHECK (change_kind IN ('Inserted', 'Updated', 'Removed')),
            CONSTRAINT CK_match_changes_value_for_insert
                CHECK (
                    change_kind <> 'Inserted'
                    OR (old_value IS NULL AND new_value IS NOT NULL)
                )
        );
    END;

    IF OBJECT_ID(N'dbo.sync_checkpoints', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.sync_checkpoints
        (
            sync_checkpoint_id bigint IDENTITY(1, 1) NOT NULL
                CONSTRAINT PK_sync_checkpoints PRIMARY KEY,
            provider nvarchar(50) NOT NULL,
            competition_season_id bigint NOT NULL,
            scope_key nvarchar(250) NOT NULL,
            matchday_number int NULL,
            competition_stage nvarchar(100) NULL,
            last_successful_snapshot_id bigint NULL,
            last_successful_import_run_id bigint NULL,
            last_source_update_utc datetime2(7) NULL,
            last_processed_at_utc datetime2(7) NULL,
            updated_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_sync_checkpoints_updated_at_utc DEFAULT (SYSUTCDATETIME()),
            checkpoint_version rowversion NOT NULL,
            CONSTRAINT FK_sync_checkpoints_competition_seasons
                FOREIGN KEY (competition_season_id)
                REFERENCES dbo.competition_seasons (competition_season_id),
            CONSTRAINT FK_sync_checkpoints_source_snapshots
                FOREIGN KEY (last_successful_snapshot_id)
                REFERENCES dbo.source_snapshots (source_snapshot_id),
            CONSTRAINT FK_sync_checkpoints_import_runs
                FOREIGN KEY (last_successful_import_run_id)
                REFERENCES dbo.import_runs (import_run_id),
            CONSTRAINT UQ_sync_checkpoints_provider_scope
                UNIQUE (provider, scope_key),
            CONSTRAINT CK_sync_checkpoints_provider_not_blank
                CHECK (LEN(LTRIM(RTRIM(provider))) > 0),
            CONSTRAINT CK_sync_checkpoints_scope_not_blank
                CHECK (LEN(LTRIM(RTRIM(scope_key))) > 0),
            CONSTRAINT CK_sync_checkpoints_matchday_positive
                CHECK (matchday_number IS NULL OR matchday_number > 0)
        );
    END;

    IF OBJECT_ID(N'dbo.match_notes', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.match_notes
        (
            match_note_id bigint IDENTITY(1, 1) NOT NULL
                CONSTRAINT PK_match_notes PRIMARY KEY,
            match_id bigint NOT NULL,
            note_text nvarchar(4000) NOT NULL,
            created_by nvarchar(256) NULL,
            is_archived bit NOT NULL
                CONSTRAINT DF_match_notes_is_archived DEFAULT (0),
            created_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_match_notes_created_at_utc DEFAULT (SYSUTCDATETIME()),
            updated_at_utc datetime2(7) NOT NULL
                CONSTRAINT DF_match_notes_updated_at_utc DEFAULT (SYSUTCDATETIME()),
            CONSTRAINT FK_match_notes_matches
                FOREIGN KEY (match_id)
                REFERENCES dbo.matches (match_id),
            CONSTRAINT CK_match_notes_text_not_blank
                CHECK (LEN(LTRIM(RTRIM(note_text))) > 0)
        );
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.competition_seasons', N'U')
          AND name = N'IX_competition_seasons_source_lookup'
    )
    BEGIN
        CREATE INDEX IX_competition_seasons_source_lookup
            ON dbo.competition_seasons (source_league_id, season_start_year);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.teams', N'U')
          AND name = N'IX_teams_name'
    )
    BEGIN
        CREATE INDEX IX_teams_name
            ON dbo.teams (team_name);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.matches', N'U')
          AND name = N'IX_matches_competition_kickoff'
    )
    BEGIN
        CREATE INDEX IX_matches_competition_kickoff
            ON dbo.matches (competition_season_id, kickoff_utc);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.matches', N'U')
          AND name = N'IX_matches_home_team_kickoff'
    )
    BEGIN
        CREATE INDEX IX_matches_home_team_kickoff
            ON dbo.matches (home_team_id, kickoff_utc);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.matches', N'U')
          AND name = N'IX_matches_away_team_kickoff'
    )
    BEGIN
        CREATE INDEX IX_matches_away_team_kickoff
            ON dbo.matches (away_team_id, kickoff_utc);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.matches', N'U')
          AND name = N'IX_matches_matchday_stage'
    )
    BEGIN
        CREATE INDEX IX_matches_matchday_stage
            ON dbo.matches (competition_season_id, matchday_number, competition_stage);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.match_results', N'U')
          AND name = N'IX_match_results_match_type'
    )
    BEGIN
        CREATE INDEX IX_match_results_match_type
            ON dbo.match_results (match_id, result_type_kind);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.match_goals', N'U')
          AND name = N'IX_match_goals_match_minute'
    )
    BEGIN
        CREATE INDEX IX_match_goals_match_minute
            ON dbo.match_goals (match_id, match_minute);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.source_snapshots', N'U')
          AND name = N'IX_source_snapshots_scope_retrieved'
    )
    BEGIN
        CREATE INDEX IX_source_snapshots_scope_retrieved
            ON dbo.source_snapshots
            (
                provider,
                source_league_id,
                season_start_year,
                matchday_number,
                retrieved_at_utc DESC
            );
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.source_snapshots', N'U')
          AND name = N'IX_source_snapshots_hash'
    )
    BEGIN
        CREATE INDEX IX_source_snapshots_hash
            ON dbo.source_snapshots (provider, sha256, retrieved_at_utc);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.import_runs', N'U')
          AND name = N'IX_import_runs_scope_started'
    )
    BEGIN
        CREATE INDEX IX_import_runs_scope_started
            ON dbo.import_runs (competition_season_id, matchday_number, started_at_utc DESC);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.import_runs', N'U')
          AND name = N'IX_import_runs_status_started'
    )
    BEGIN
        CREATE INDEX IX_import_runs_status_started
            ON dbo.import_runs (status, started_at_utc DESC);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.import_runs', N'U')
          AND name = N'IX_import_runs_snapshot'
    )
    BEGIN
        CREATE INDEX IX_import_runs_snapshot
            ON dbo.import_runs (source_snapshot_id);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.validation_issues', N'U')
          AND name = N'IX_validation_issues_import'
    )
    BEGIN
        CREATE INDEX IX_validation_issues_import
            ON dbo.validation_issues (import_run_id, severity, created_at_utc DESC);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.validation_issues', N'U')
          AND name = N'IX_validation_issues_snapshot_record'
    )
    BEGIN
        CREATE INDEX IX_validation_issues_snapshot_record
            ON dbo.validation_issues (source_snapshot_id, source_record_type, source_record_id);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.match_changes', N'U')
          AND name = N'IX_match_changes_history'
    )
    BEGIN
        CREATE INDEX IX_match_changes_history
            ON dbo.match_changes (match_id, observed_at_utc DESC);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.match_changes', N'U')
          AND name = N'IX_match_changes_import'
    )
    BEGIN
        CREATE INDEX IX_match_changes_import
            ON dbo.match_changes (import_run_id, observed_at_utc DESC);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.sync_checkpoints', N'U')
          AND name = N'IX_sync_checkpoints_lookup'
    )
    BEGIN
        CREATE INDEX IX_sync_checkpoints_lookup
            ON dbo.sync_checkpoints (competition_season_id, matchday_number, competition_stage);
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.match_notes', N'U')
          AND name = N'IX_match_notes_match_updated'
    )
    BEGIN
        CREATE INDEX IX_match_notes_match_updated
            ON dbo.match_notes (match_id, updated_at_utc DESC);
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
    BEGIN
        ROLLBACK TRANSACTION;
    END;

    THROW;
END CATCH;
GO
