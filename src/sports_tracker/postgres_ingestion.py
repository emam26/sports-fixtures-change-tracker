"""PostgreSQL implementation of the existing transactional import-store contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from .ingestion import (
    ChildState,
    FixtureData,
    GoalData,
    ImportSummary,
    MatchState,
    ParsedSnapshot,
    ResultData,
    SnapshotImportProcessor,
    TeamData,
    ValidationIssue,
    _from_database_datetime,
    _goal_fields,
    _result_fields,
    _safe_error_summary,
    _serialize_value,
)


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return row[index]


def _postgres_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(UTC)


class PostgreSQLImportStore:
    """PostgreSQL store preserving the SQL Server import-store semantics."""

    def __init__(self, connection: Any, provider: str = "OpenLigaDB") -> None:
        self.connection = connection
        self.provider = provider
        self._operation = "PostgreSQLImportStore.initialization"

    @property
    def last_operation(self) -> str:
        return self._operation

    @property
    def cursor(self) -> Any:
        return self.connection.cursor()

    def begin(self) -> None:
        self._operation = "PostgreSQLImportStore.begin"
        self.connection.autocommit = False

    def commit(self) -> None:
        self._operation = "PostgreSQLImportStore.commit"
        self.connection.commit()

    def rollback(self) -> None:
        self._operation = "PostgreSQLImportStore.rollback"
        self.connection.rollback()

    def _insert_id(self, statement: str, parameters: Sequence[Any]) -> int:
        cursor = self.cursor
        cursor.execute(statement, tuple(parameters))
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("PostgreSQL did not return the inserted identity")
        return int(_row_value(row, "new_id", 0))

    def ensure_snapshot(self, parsed: ParsedSnapshot) -> int:
        self._operation = "PostgreSQLImportStore.ensure_snapshot"
        metadata = parsed.metadata
        local_directory = str(parsed.directory)
        cursor = self.cursor
        cursor.execute(
            """
            SELECT source_snapshot_id, sha256, retrieved_at_utc
            FROM source_snapshots
            WHERE provider = %s AND local_directory = %s
            """,
            (metadata.provider, local_directory),
        )
        row = cursor.fetchone()
        retrieved_at = _postgres_datetime(metadata.retrieved_at_utc)
        if row is not None:
            stored_hash = _row_value(row, "sha256", 1)
            stored_time = _row_value(row, "retrieved_at_utc", 2)
            if str(stored_hash).lower() != metadata.sha256 or stored_time != retrieved_at:
                raise RuntimeError(
                    "existing source snapshot metadata does not match the local snapshot"
                )
            return int(_row_value(row, "source_snapshot_id", 0))
        return self._insert_id(
            """
            INSERT INTO source_snapshots
            (
                provider, provider_shortcut, source_league_id, season_start_year,
                matchday_number, source_url, retrieved_at_utc, http_status,
                content_type, byte_count, sha256, local_directory, response_path,
                metadata_path
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING source_snapshot_id AS new_id
            """,
            (
                metadata.provider,
                metadata.shortcut,
                parsed.source_league_id,
                metadata.season,
                metadata.matchday,
                metadata.url,
                retrieved_at,
                metadata.http_status,
                metadata.content_type,
                metadata.byte_count,
                metadata.sha256,
                local_directory,
                str(parsed.directory / "response.json"),
                str(parsed.directory / "metadata.json"),
            ),
        )

    def ensure_competition(self, provider: str, shortcut: str, name: str) -> int:
        self._operation = "PostgreSQLImportStore.ensure_competition"
        cursor = self.cursor
        cursor.execute(
            """
            SELECT competition_id
            FROM competitions
            WHERE provider = %s AND provider_shortcut = %s
            """,
            (provider, shortcut),
        )
        row = cursor.fetchone()
        if row is not None:
            return int(_row_value(row, "competition_id", 0))
        return self._insert_id(
            """
            INSERT INTO competitions (provider, provider_shortcut, competition_name)
            VALUES (%s, %s, %s)
            RETURNING competition_id AS new_id
            """,
            (provider, shortcut, name),
        )

    def ensure_season(self, competition_id: int, source_league_id: int, season: int) -> int:
        self._operation = "PostgreSQLImportStore.ensure_season"
        cursor = self.cursor
        cursor.execute(
            """
            SELECT competition_season_id
            FROM competition_seasons
            WHERE competition_id = %s
              AND source_league_id = %s
              AND season_start_year = %s
            """,
            (competition_id, source_league_id, season),
        )
        row = cursor.fetchone()
        if row is not None:
            return int(_row_value(row, "competition_season_id", 0))
        return self._insert_id(
            """
            INSERT INTO competition_seasons
                (competition_id, source_league_id, season_start_year)
            VALUES (%s, %s, %s)
            RETURNING competition_season_id AS new_id
            """,
            (competition_id, source_league_id, season),
        )

    def find_successful_run(self, source_snapshot_id: int) -> int | None:
        self._operation = "PostgreSQLImportStore.find_successful_run"
        cursor = self.cursor
        cursor.execute(
            """
            SELECT import_run_id
            FROM import_runs
            WHERE source_snapshot_id = %s AND status = 'Succeeded'
            ORDER BY import_run_id
            LIMIT 1
            """,
            (source_snapshot_id,),
        )
        row = cursor.fetchone()
        return None if row is None else int(_row_value(row, "import_run_id", 0))

    def start_run(
        self,
        parsed: ParsedSnapshot,
        competition_season_id: int,
        source_snapshot_id: int,
        is_replay: bool,
        replay_of_import_run_id: int | None,
    ) -> int:
        self._operation = "PostgreSQLImportStore.start_run"
        return self._insert_id(
            """
            INSERT INTO import_runs
            (
                provider, competition_season_id, source_snapshot_id, matchday_number,
                requested_url, status, is_replay, replay_of_import_run_id
            )
            VALUES (%s, %s, %s, %s, %s, 'Started', %s, %s)
            RETURNING import_run_id AS new_id
            """,
            (
                parsed.metadata.provider,
                competition_season_id,
                source_snapshot_id,
                parsed.metadata.matchday,
                parsed.metadata.url,
                is_replay,
                replay_of_import_run_id,
            ),
        )

    def record_issues(
        self,
        import_run_id: int,
        source_snapshot_id: int,
        issues: Sequence[ValidationIssue],
    ) -> None:
        self._operation = "PostgreSQLImportStore.record_issues"
        cursor = self.cursor
        for issue in issues:
            cursor.execute(
                """
                INSERT INTO validation_issues
                (
                    import_run_id, source_snapshot_id, provider, source_record_type,
                    source_record_id, field_name, issue_code, severity, issue_message,
                    source_value
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    import_run_id,
                    source_snapshot_id,
                    self.provider,
                    issue.source_record_type,
                    issue.source_record_id,
                    issue.field_name,
                    issue.code,
                    issue.severity,
                    issue.message,
                    issue.source_value,
                ),
            )

    def finish_run(
        self,
        import_run_id: int,
        status: str,
        counters: ImportSummary,
        failure_phase: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        self._operation = "PostgreSQLImportStore.finish_run"
        self.cursor.execute(
            """
            UPDATE import_runs
            SET completed_at_utc = CURRENT_TIMESTAMP,
                status = %s,
                matches_seen = %s,
                matches_inserted = %s,
                matches_updated = %s,
                matches_unchanged = %s,
                matches_rejected = %s,
                results_seen = %s,
                validation_issue_count = %s,
                failure_phase = %s,
                error_summary = %s
            WHERE import_run_id = %s
            """,
            (
                status,
                counters.matches_seen,
                counters.matches_inserted,
                counters.matches_updated,
                counters.matches_unchanged,
                counters.matches_rejected,
                counters.results_seen,
                counters.validation_issue_count,
                failure_phase,
                error_summary,
                import_run_id,
            ),
        )

    def get_match(self, provider: str, provider_match_id: int) -> MatchState | None:
        self._operation = "PostgreSQLImportStore.get_match"
        cursor = self.cursor
        cursor.execute(
            """
            SELECT m.match_id,
                   t1.provider_team_id AS home_provider_team_id,
                   t2.provider_team_id AS away_provider_team_id,
                   m.matchday_number, m.competition_stage, m.source_group_id,
                   m.source_group_order_id, m.source_group_name, m.kickoff_utc,
                   m.source_match_is_finished, m.source_last_update_utc,
                   m.source_last_update_raw, m.source_time_zone_id, m.location
            FROM matches AS m
            INNER JOIN teams AS t1 ON t1.team_id = m.home_team_id
            INNER JOIN teams AS t2 ON t2.team_id = m.away_team_id
            WHERE m.provider = %s AND m.provider_match_id = %s
            """,
            (provider, provider_match_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        fields = {
            "home_team_id": int(_row_value(row, "home_provider_team_id", 1)),
            "away_team_id": int(_row_value(row, "away_provider_team_id", 2)),
            "matchday_number": _row_value(row, "matchday_number", 3),
            "competition_stage": _row_value(row, "competition_stage", 4),
            "source_group_id": _row_value(row, "source_group_id", 5),
            "source_group_order_id": _row_value(row, "source_group_order_id", 6),
            "source_group_name": _row_value(row, "source_group_name", 7),
            "kickoff_utc": _from_database_datetime(_row_value(row, "kickoff_utc", 8)),
            "source_match_is_finished": bool(_row_value(row, "source_match_is_finished", 9)),
            "source_last_update_utc": _from_database_datetime(
                _row_value(row, "source_last_update_utc", 10)
            ),
            "source_last_update_raw": _row_value(row, "source_last_update_raw", 11),
            "source_time_zone_id": _row_value(row, "source_time_zone_id", 12),
            "location": _row_value(row, "location", 13),
        }
        return MatchState(int(_row_value(row, "match_id", 0)), fields)

    def upsert_team(self, team: TeamData) -> int:
        self._operation = "PostgreSQLImportStore.upsert_team"
        cursor = self.cursor
        cursor.execute(
            """
            SELECT team_id, team_name, short_name, tla, team_group_name,
                   team_icon_url, wikidata_id
            FROM teams
            WHERE provider = %s AND provider_team_id = %s
            """,
            (self.provider, team.provider_team_id),
        )
        row = cursor.fetchone()
        values = (
            team.team_name,
            team.short_name,
            team.tla,
            team.team_group_name,
            team.team_icon_url,
            team.wikidata_id,
        )
        if row is not None:
            current = tuple(
                _row_value(row, key, index)
                for index, key in enumerate(
                    (
                        "team_name",
                        "short_name",
                        "tla",
                        "team_group_name",
                        "team_icon_url",
                        "wikidata_id",
                    ),
                    start=1,
                )
            )
            effective_values = (*values[:4], team.team_icon_url or current[4], values[5])
            if current != effective_values:
                cursor.execute(
                    """
                    UPDATE teams
                    SET team_name = %s, short_name = %s, tla = %s,
                        team_group_name = %s, team_icon_url = %s, wikidata_id = %s,
                        updated_at_utc = CURRENT_TIMESTAMP
                    WHERE team_id = %s
                    """,
                    (*effective_values, int(_row_value(row, "team_id", 0))),
                )
            return int(_row_value(row, "team_id", 0))
        return self._insert_id(
            """
            INSERT INTO teams
            (
                provider, provider_team_id, team_name, short_name, tla,
                team_group_name, team_icon_url, wikidata_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING team_id AS new_id
            """,
            (self.provider, team.provider_team_id, *values),
        )

    def insert_match(
        self,
        fixture: FixtureData,
        competition_season_id: int,
        home_team_id: int,
        away_team_id: int,
    ) -> int:
        self._operation = "PostgreSQLImportStore.insert_match"
        return self._insert_id(
            """
            INSERT INTO matches
            (
                competition_season_id, provider, provider_match_id, home_team_id,
                away_team_id, matchday_number, source_group_id, source_group_order_id,
                source_group_name, kickoff_utc, source_match_is_finished,
                source_last_update_raw, source_time_zone_id, location
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING match_id AS new_id
            """,
            (
                competition_season_id,
                self.provider,
                fixture.provider_match_id,
                home_team_id,
                away_team_id,
                fixture.matchday_number,
                fixture.source_group_id,
                fixture.source_group_order_id,
                fixture.source_group_name,
                _postgres_datetime(fixture.kickoff_utc),
                fixture.match_is_finished,
                fixture.source_last_update_raw,
                fixture.source_time_zone_id,
                fixture.location,
            ),
        )

    def update_match(
        self,
        match_id: int,
        fixture: FixtureData,
        home_team_id: int,
        away_team_id: int,
    ) -> None:
        self._operation = "PostgreSQLImportStore.update_match"
        self.cursor.execute(
            """
            UPDATE matches
            SET home_team_id = %s, away_team_id = %s, matchday_number = %s,
                source_group_id = %s, source_group_order_id = %s,
                source_group_name = %s, kickoff_utc = %s,
                source_match_is_finished = %s, source_last_update_utc = %s,
                source_last_update_raw = %s, source_time_zone_id = %s,
                location = %s, updated_at_utc = CURRENT_TIMESTAMP
            WHERE match_id = %s
            """,
            (
                home_team_id,
                away_team_id,
                fixture.matchday_number,
                fixture.source_group_id,
                fixture.source_group_order_id,
                fixture.source_group_name,
                _postgres_datetime(fixture.kickoff_utc),
                fixture.match_is_finished,
                _postgres_datetime(fixture.source_last_update_utc),
                fixture.source_last_update_raw,
                fixture.source_time_zone_id,
                fixture.location,
                match_id,
            ),
        )

    def get_result(self, match_id: int, provider_result_id: int) -> ChildState | None:
        self._operation = "PostgreSQLImportStore.get_result"
        cursor = self.cursor
        cursor.execute(
            """
            SELECT match_result_id, result_type_id, result_type_kind, result_order_id,
                   result_name, result_description, points_team1, points_team2
            FROM match_results
            WHERE match_id = %s AND provider_result_id = %s
            """,
            (match_id, provider_result_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return ChildState(
            int(_row_value(row, "match_result_id", 0)),
            {
                key: _row_value(row, key, index)
                for index, key in enumerate(
                    (
                        "result_type_id",
                        "result_type_kind",
                        "result_order_id",
                        "result_name",
                        "result_description",
                        "points_team1",
                        "points_team2",
                    ),
                    start=1,
                )
            },
        )

    def insert_result(self, match_id: int, result: ResultData) -> int:
        self._operation = "PostgreSQLImportStore.insert_result"
        return self._insert_id(
            """
            INSERT INTO match_results
            (
                match_id, provider, provider_result_id, result_type_id,
                result_type_kind, result_order_id, result_name, result_description,
                points_team1, points_team2
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING match_result_id AS new_id
            """,
            (
                match_id,
                self.provider,
                result.provider_result_id,
                *tuple(_result_fields(result).values()),
            ),
        )

    def update_result(self, child_id: int, result: ResultData) -> None:
        self._operation = "PostgreSQLImportStore.update_result"
        self.cursor.execute(
            """
            UPDATE match_results
            SET result_type_id = %s, result_type_kind = %s, result_order_id = %s,
                result_name = %s, result_description = %s,
                points_team1 = %s, points_team2 = %s
            WHERE match_result_id = %s
            """,
            (*tuple(_result_fields(result).values()), child_id),
        )

    def get_goal(self, match_id: int, provider_goal_id: int) -> ChildState | None:
        self._operation = "PostgreSQLImportStore.get_goal"
        cursor = self.cursor
        cursor.execute(
            """
            SELECT match_goal_id, score_team1, score_team2, match_minute,
                   goal_getter_provider_id, goal_getter_name, scoring_team_id,
                   is_penalty, is_own_goal, is_overtime, comment
            FROM match_goals
            WHERE match_id = %s AND provider_goal_id = %s
            """,
            (match_id, provider_goal_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        keys = (
            "score_team1",
            "score_team2",
            "match_minute",
            "goal_getter_provider_id",
            "goal_getter_name",
            "scoring_team_id",
            "is_penalty",
            "is_own_goal",
            "is_overtime",
            "comment",
        )
        return ChildState(
            int(_row_value(row, "match_goal_id", 0)),
            {key: _row_value(row, key, index) for index, key in enumerate(keys, start=1)},
        )

    def insert_goal(self, match_id: int, goal: GoalData, scoring_team_id: int | None) -> int:
        self._operation = "PostgreSQLImportStore.insert_goal"
        return self._insert_id(
            """
            INSERT INTO match_goals
            (
                match_id, provider, provider_goal_id, score_team1, score_team2,
                match_minute, goal_getter_provider_id, goal_getter_name,
                scoring_team_id, is_penalty, is_own_goal, is_overtime, comment
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING match_goal_id AS new_id
            """,
            (
                match_id,
                self.provider,
                goal.provider_goal_id,
                *tuple(_goal_fields(goal, scoring_team_id).values()),
            ),
        )

    def update_goal(self, child_id: int, goal: GoalData, scoring_team_id: int | None) -> None:
        self._operation = "PostgreSQLImportStore.update_goal"
        self.cursor.execute(
            """
            UPDATE match_goals
            SET score_team1 = %s, score_team2 = %s, match_minute = %s,
                goal_getter_provider_id = %s, goal_getter_name = %s,
                scoring_team_id = %s, is_penalty = %s, is_own_goal = %s,
                is_overtime = %s, comment = %s
            WHERE match_goal_id = %s
            """,
            (*tuple(_goal_fields(goal, scoring_team_id).values()), child_id),
        )

    def record_change(
        self,
        match_id: int,
        import_run_id: int,
        source_snapshot_id: int,
        field_name: str,
        change_kind: str,
        old_value: Any,
        new_value: Any,
        observed_at_utc: datetime,
    ) -> None:
        self._operation = "PostgreSQLImportStore.record_change"
        self.cursor.execute(
            """
            INSERT INTO match_changes
            (
                match_id, import_run_id, source_snapshot_id, field_name, change_kind,
                old_value, new_value, observed_at_utc
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_snapshot_id, match_id, field_name, change_kind)
            DO NOTHING
            """,
            (
                match_id,
                import_run_id,
                source_snapshot_id,
                field_name[:128],
                change_kind,
                _serialize_value(old_value),
                _serialize_value(new_value),
                _postgres_datetime(observed_at_utc),
            ),
        )

    def advance_checkpoint(
        self,
        parsed: ParsedSnapshot,
        competition_season_id: int,
        source_snapshot_id: int,
        import_run_id: int,
    ) -> None:
        self._operation = "PostgreSQLImportStore.advance_checkpoint"
        scope_key = (
            f"{parsed.metadata.provider}:{parsed.metadata.shortcut}:"
            f"{parsed.metadata.season}:matchday:{parsed.metadata.matchday}"
        )
        self.cursor.execute(
            """
            INSERT INTO sync_checkpoints
            (
                provider, competition_season_id, scope_key, matchday_number,
                last_successful_snapshot_id, last_successful_import_run_id,
                last_source_update_utc, last_processed_at_utc, checkpoint_version
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)
            ON CONFLICT (provider, scope_key) DO UPDATE SET
                last_successful_snapshot_id = EXCLUDED.last_successful_snapshot_id,
                last_successful_import_run_id = EXCLUDED.last_successful_import_run_id,
                last_source_update_utc = COALESCE(
                    EXCLUDED.last_source_update_utc,
                    sync_checkpoints.last_source_update_utc
                ),
                last_processed_at_utc = EXCLUDED.last_processed_at_utc,
                updated_at_utc = CURRENT_TIMESTAMP,
                checkpoint_version = sync_checkpoints.checkpoint_version + 1
            """,
            (
                parsed.metadata.provider,
                competition_season_id,
                scope_key,
                parsed.metadata.matchday,
                source_snapshot_id,
                import_run_id,
                _postgres_datetime(parsed.source_last_change_utc),
                _postgres_datetime(parsed.metadata.retrieved_at_utc),
            ),
        )

    def record_failed_run(
        self,
        parsed: ParsedSnapshot,
        error_summary: str,
        issues: Sequence[ValidationIssue] = (),
    ) -> None:
        """Persist failure provenance only after primary transaction rollback."""

        self._operation = "PostgreSQLImportStore.record_failed_run"
        try:
            snapshot_id = self.ensure_snapshot(parsed)
            competition_id = self.ensure_competition(
                parsed.metadata.provider,
                parsed.metadata.shortcut,
                parsed.competition_name,
            )
            season_id = self.ensure_season(
                competition_id,
                parsed.source_league_id,
                parsed.metadata.season,
            )
            previous_run_id = self.find_successful_run(snapshot_id)
            run_id = self.start_run(
                parsed,
                season_id,
                snapshot_id,
                previous_run_id is not None,
                previous_run_id,
            )
            failure_issue = ValidationIssue("database-import-failure", error_summary, "Error")
            all_issues = (*issues, failure_issue)
            self.record_issues(run_id, snapshot_id, all_issues)
            counters = ImportSummary(
                status="Failed",
                import_run_id=run_id,
                source_snapshot_id=snapshot_id,
                matches_seen=len(parsed.matches),
                matches_inserted=0,
                matches_updated=0,
                matches_unchanged=0,
                matches_rejected=0,
                results_seen=0,
                goals_seen=0,
                changes_recorded=0,
                validation_issue_count=len(all_issues),
                issues=all_issues,
            )
            self.finish_run(run_id, "Failed", counters, "database", error_summary)
            self.connection.commit()
        except Exception:
            try:
                self.connection.rollback()
            except Exception as rollback_error:
                raise RuntimeError(
                    "PostgreSQL failed-import provenance rollback failed: "
                    f"{_safe_error_summary(rollback_error)}"
                ) from rollback_error
            raise


def import_snapshot_with_postgresql(parsed: ParsedSnapshot, settings: Any) -> ImportSummary:
    """Import one parsed snapshot through the PostgreSQL store."""

    from .postgres import postgresql_connection

    with postgresql_connection(settings) as connection:
        store = PostgreSQLImportStore(connection, parsed.metadata.provider)
        return SnapshotImportProcessor(store).import_snapshot(parsed)
