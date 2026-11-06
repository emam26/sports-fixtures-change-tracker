"""Parameterized SQL Server queries aligned with the deployed Stage 2 schema."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from typing import Any, Protocol

_LOGGER = logging.getLogger(__name__)


class Repository(Protocol):
    def health(self) -> None: ...

    def competitions(self) -> list[dict[str, Any]]: ...

    def matchdays(self, competition_season_id: int | None) -> list[dict[str, Any]]: ...

    def matches(
        self,
        *,
        competition_season_id: int | None,
        matchday: int | None,
        finished: bool | None,
        search: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]: ...

    def dashboard_summary(self, competition_season_id: int | None) -> dict[str, Any]: ...

    def match(self, match_id: int) -> dict[str, Any] | None: ...

    def changes(self, match_id: int) -> list[dict[str, Any]]: ...

    def match_changes(
        self,
        *,
        competition_season_id: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]: ...

    def sync_checkpoints(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]: ...

    def import_runs(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]: ...

    def validation_issues(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]: ...

    def notes(self, match_id: int) -> list[dict[str, Any]]: ...

    def create_note(self, match_id: int, note_text: str, created_by: str) -> dict[str, Any]: ...

    def update_note(self, note_id: int, note_text: str) -> dict[str, Any] | None: ...

    def archive_note(self, note_id: int) -> bool: ...


def _rows(cursor: Any) -> list[dict[str, Any]]:
    while cursor.description is None:
        if not cursor.nextset():
            return []
    names = [column[0] for column in cursor.description]
    records: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        record = dict(zip(names, row, strict=True))
        for name, value in record.items():
            if name.endswith("_utc") and isinstance(value, datetime) and value.tzinfo is None:
                record[name] = value.replace(tzinfo=UTC)
        records.append(record)
    return records


def _like_pattern(value: str) -> str:
    escaped = value.replace("~", "~~").replace("%", "~%").replace("_", "~_")
    return f"%{escaped.replace('[', '~[')}%"


class SQLServerRepository:
    """Small query layer; every call owns and closes its SQL Server connection."""

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory

    def _read(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with closing(self._connection_factory()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, params)
            return _rows(cursor)

    def health(self) -> None:
        self._read("SELECT CAST(1 AS int) AS ready;")

    def competitions(self) -> list[dict[str, Any]]:
        return self._read(
            """
            SELECT cs.competition_season_id,
                   c.provider,
                   c.competition_name AS name,
                   c.provider_shortcut AS shortcut,
                   COALESCE(
                       cs.season_label,
                       CONVERT(nvarchar(20), cs.season_start_year)
                   ) AS season,
                   cs.source_league_id AS provider_league_id
            FROM dbo.competition_seasons AS cs
            INNER JOIN dbo.competitions AS c
                ON c.competition_id = cs.competition_id
            WHERE c.is_active = 1
            ORDER BY cs.season_start_year DESC, c.competition_name;
            """
        )

    def matchdays(self, competition_season_id: int | None) -> list[dict[str, Any]]:
        predicates = ["m.matchday_number IS NOT NULL"]
        params: list[Any] = []
        if competition_season_id is not None:
            predicates.append("m.competition_season_id = ?")
            params.append(competition_season_id)
        where = " AND ".join(predicates)
        return self._read(
            f"""
            SELECT m.competition_season_id,
                   m.matchday_number,
                   COUNT_BIG(*) AS match_count,
                   SUM(CASE WHEN m.source_match_is_finished = 1 THEN 1 ELSE 0 END)
                       AS finished_count,
                   SUM(CASE WHEN m.source_match_is_finished = 0 THEN 1 ELSE 0 END)
                       AS unfinished_count,
                   MIN(m.kickoff_utc) AS first_kickoff_utc,
                   MAX(m.kickoff_utc) AS last_kickoff_utc
            FROM dbo.matches AS m
            WHERE {where}
            GROUP BY m.competition_season_id, m.matchday_number
            ORDER BY m.competition_season_id, m.matchday_number;
            """,
            tuple(params),
        )

    def matches(
        self,
        *,
        competition_season_id: int | None,
        matchday: int | None,
        finished: bool | None,
        search: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        predicates = ["1 = 1"]
        params: list[Any] = []
        if competition_season_id is not None:
            predicates.append("m.competition_season_id = ?")
            params.append(competition_season_id)
        if matchday is not None:
            predicates.append("m.matchday_number = ?")
            params.append(matchday)
        if finished is not None:
            predicates.append("m.source_match_is_finished = ?")
            params.append(finished)
        if search:
            predicates.append("(ht.team_name LIKE ? ESCAPE '~' OR at.team_name LIKE ? ESCAPE '~')")
            term = _like_pattern(search)
            params.extend((term, term))
        where = " AND ".join(predicates)
        base = f"""
            FROM dbo.matches AS m
            INNER JOIN dbo.teams AS ht ON ht.team_id = m.home_team_id
            INNER JOIN dbo.teams AS at ON at.team_id = m.away_team_id
            OUTER APPLY (
                SELECT TOP (1)
                       mr.points_team1 AS home_score,
                       mr.points_team2 AS away_score
                FROM dbo.match_results AS mr
                WHERE mr.match_id = m.match_id
                  AND mr.result_type_kind = N'After90Minutes'
                ORDER BY mr.result_order_id DESC, mr.match_result_id DESC
            ) AS final_result
            WHERE {where}
        """
        total = self._read(f"SELECT COUNT_BIG(*) AS total {base}", tuple(params))[0]
        items = self._read(
            f"""
            SELECT m.match_id,
                   m.provider_match_id,
                   m.matchday_number,
                   m.competition_stage AS stage_name,
                   m.kickoff_utc,
                   m.source_match_is_finished AS is_finished,
                   ht.team_name AS home_team,
                   at.team_name AS away_team,
                   final_result.home_score,
                   final_result.away_score,
                   m.source_last_update_utc AS last_source_update_utc
            {base}
            ORDER BY CASE WHEN m.kickoff_utc IS NULL THEN 1 ELSE 0 END,
                     m.kickoff_utc,
                     m.match_id
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY;
            """,
            (*params, offset, limit),
        )
        return items, int(total["total"])

    def dashboard_summary(self, competition_season_id: int | None) -> dict[str, Any]:
        match_where = "1 = 1"
        checkpoint_where = "1 = 1"
        parameters: tuple[Any, ...] = ()
        if competition_season_id is not None:
            match_where = "m.competition_season_id = ?"
            checkpoint_where = "sc.competition_season_id = ?"
            parameters = (competition_season_id,)

        def read_component(operation: str, sql: str) -> list[dict[str, Any]]:
            try:
                return self._read(sql, parameters)
            except Exception as exc:
                _LOGGER.error(
                    "Dashboard summary read failed (operation=%s, error_type=%s)",
                    operation,
                    type(exc).__name__,
                )
                raise

        fixture_counts = read_component(
            "fixture-counts",
            f"""
            SELECT COUNT_BIG(*) AS total_fixtures,
                   COALESCE(
                       SUM(CASE WHEN m.source_match_is_finished = 1 THEN 1 ELSE 0 END),
                       0
                   ) AS finished_fixtures,
                   COALESCE(
                       SUM(CASE WHEN m.source_match_is_finished = 0 THEN 1 ELSE 0 END),
                       0
                   ) AS upcoming_fixtures
            FROM dbo.matches AS m
            WHERE {match_where};
            """,
        )[0]
        goal_counts = read_component(
            "goal-counts",
            f"""
            SELECT COUNT_BIG(*) AS goals_recorded
            FROM dbo.match_goals AS mg
            INNER JOIN dbo.matches AS m ON m.match_id = mg.match_id
            WHERE {match_where};
            """,
        )[0]
        change_counts = read_component(
            "change-counts",
            f"""
            SELECT COUNT_BIG(*) AS detected_changes,
                   COUNT_BIG(DISTINCT mc.match_id) AS changed_fixtures
            FROM dbo.match_changes AS mc
            INNER JOIN dbo.matches AS m ON m.match_id = mc.match_id
            WHERE {match_where};
            """,
        )[0]
        checkpoints = read_component(
            "latest-successful-checkpoint",
            f"""
            SELECT TOP (1)
                   sc.last_processed_at_utc AS latest_successful_sync_at_utc,
                   sc.last_successful_snapshot_id,
                   sc.last_successful_import_run_id
            FROM dbo.sync_checkpoints AS sc
            WHERE sc.last_successful_import_run_id IS NOT NULL
              AND sc.last_processed_at_utc IS NOT NULL
              AND {checkpoint_where}
            ORDER BY sc.last_processed_at_utc DESC, sc.sync_checkpoint_id DESC;
            """,
        )
        checkpoint = checkpoints[0] if checkpoints else {}
        return {
            "total_fixtures": int(fixture_counts["total_fixtures"] or 0),
            "finished_fixtures": int(fixture_counts["finished_fixtures"] or 0),
            "upcoming_fixtures": int(fixture_counts["upcoming_fixtures"] or 0),
            "goals_recorded": int(goal_counts["goals_recorded"] or 0),
            "detected_changes": int(change_counts["detected_changes"] or 0),
            "changed_fixtures": int(change_counts["changed_fixtures"] or 0),
            "latest_successful_sync_at_utc": checkpoint.get("latest_successful_sync_at_utc"),
            "latest_successful_snapshot_id": checkpoint.get("latest_successful_snapshot_id"),
            "latest_successful_import_run_id": checkpoint.get("latest_successful_import_run_id"),
        }

    def match(self, match_id: int) -> dict[str, Any] | None:
        records = self._read(
            """
            SELECT m.match_id,
                   m.provider_match_id,
                   m.matchday_number,
                   m.competition_stage AS stage_name,
                   m.kickoff_utc,
                   m.source_match_is_finished AS is_finished,
                   ht.team_name AS home_team,
                   at.team_name AS away_team,
                   final_result.home_score,
                   final_result.away_score,
                   m.source_last_update_utc AS last_source_update_utc,
                   m.location AS venue
            FROM dbo.matches AS m
            INNER JOIN dbo.teams AS ht ON ht.team_id = m.home_team_id
            INNER JOIN dbo.teams AS at ON at.team_id = m.away_team_id
            OUTER APPLY (
                SELECT TOP (1)
                       mr.points_team1 AS home_score,
                       mr.points_team2 AS away_score
                FROM dbo.match_results AS mr
                WHERE mr.match_id = m.match_id
                  AND mr.result_type_kind = N'After90Minutes'
                ORDER BY mr.result_order_id DESC, mr.match_result_id DESC
            ) AS final_result
            WHERE m.match_id = ?;
            """,
            (match_id,),
        )
        if not records:
            return None
        record = records[0]
        record["results"] = self._read(
            """
            SELECT result_type_kind AS result_type,
                   COALESCE(result_name, result_description) AS result_name,
                   points_team1 AS home_score,
                   points_team2 AS away_score
            FROM dbo.match_results
            WHERE match_id = ?
            ORDER BY result_order_id, match_result_id;
            """,
            (match_id,),
        )
        record["goals"] = self._read(
            """
            SELECT provider_goal_id,
                   score_team1 AS score_home,
                   score_team2 AS score_away,
                   match_minute AS minute,
                   goal_getter_name AS scorer_name,
                   is_penalty,
                   is_own_goal,
                   is_overtime
            FROM dbo.match_goals
            WHERE match_id = ?
            ORDER BY match_minute, provider_goal_id, match_goal_id;
            """,
            (match_id,),
        )
        return record

    def changes(self, match_id: int) -> list[dict[str, Any]]:
        return self._read(
            """
            SELECT match_change_id, field_name, change_kind, old_value,
                   new_value, observed_at_utc, source_last_update_utc,
                   import_run_id, source_snapshot_id
            FROM dbo.match_changes
            WHERE match_id = ?
            ORDER BY observed_at_utc DESC, match_change_id DESC;
            """,
            (match_id,),
        )

    def match_changes(
        self,
        *,
        competition_season_id: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        predicates = ["1 = 1"]
        params: list[Any] = []
        if competition_season_id is not None:
            predicates.append("m.competition_season_id = ?")
            params.append(competition_season_id)
        where = " AND ".join(predicates)
        base = f"""
            FROM dbo.match_changes AS mc
            INNER JOIN dbo.matches AS m ON m.match_id = mc.match_id
            INNER JOIN dbo.teams AS ht ON ht.team_id = m.home_team_id
            INNER JOIN dbo.teams AS at ON at.team_id = m.away_team_id
            INNER JOIN dbo.source_snapshots AS ss
                ON ss.source_snapshot_id = mc.source_snapshot_id
            WHERE {where}
        """
        total = self._read(f"SELECT COUNT_BIG(*) AS total {base}", tuple(params))[0]
        items = self._read(
            f"""
            SELECT mc.match_change_id,
                   m.match_id,
                   m.provider_match_id,
                   m.matchday_number,
                   ht.team_name AS home_team,
                   at.team_name AS away_team,
                   mc.field_name,
                   mc.change_kind,
                   mc.old_value,
                   mc.new_value,
                   mc.observed_at_utc,
                   mc.source_last_update_utc,
                   mc.import_run_id,
                   mc.source_snapshot_id,
                   ss.sha256 AS snapshot_sha256,
                   ss.retrieved_at_utc AS snapshot_retrieved_at_utc
            {base}
            ORDER BY mc.observed_at_utc DESC, mc.match_change_id DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY;
            """,
            (*params, offset, limit),
        )
        return items, int(total["total"])

    def sync_checkpoints(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        total = self._read("SELECT COUNT_BIG(*) AS total FROM dbo.sync_checkpoints;")[0]
        items = self._read(
            """
            SELECT sc.sync_checkpoint_id,
                   sc.provider,
                   sc.scope_key,
                   sc.matchday_number,
                   sc.last_source_update_utc,
                   sc.last_processed_at_utc,
                   sc.last_successful_snapshot_id,
                   sc.last_successful_import_run_id
            FROM dbo.sync_checkpoints AS sc
            ORDER BY sc.updated_at_utc DESC, sc.sync_checkpoint_id DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY;
            """,
            (offset, limit),
        )
        return items, int(total["total"])

    def import_runs(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        total = self._read("SELECT COUNT_BIG(*) AS total FROM dbo.import_runs;")[0]
        items = self._read(
            """
            SELECT ir.import_run_id,
                   ir.status,
                   ir.started_at_utc,
                   ir.completed_at_utc,
                   ss.sha256 AS snapshot_sha256,
                   ir.matchday_number,
                   ir.is_replay,
                   ir.matches_seen,
                   ir.matches_inserted,
                   ir.matches_updated,
                   ir.matches_unchanged,
                   ir.matches_rejected,
                   ir.results_seen,
                   ir.validation_issue_count,
                   ir.failure_phase,
                   CASE
                       WHEN ir.error_summary IS NULL THEN NULL
                       ELSE CONCAT(
                           COALESCE(ir.failure_phase, N'import'),
                           N' failure; inspect local logs'
                       )
                   END AS error_message
            FROM dbo.import_runs AS ir
            LEFT JOIN dbo.source_snapshots AS ss
                ON ss.source_snapshot_id = ir.source_snapshot_id
            ORDER BY ir.started_at_utc DESC, ir.import_run_id DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY;
            """,
            (offset, limit),
        )
        return items, int(total["total"])

    def validation_issues(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        total = self._read("SELECT COUNT_BIG(*) AS total FROM dbo.validation_issues;")[0]
        items = self._read(
            """
            SELECT validation_issue_id,
                   severity,
                   issue_code,
                   CASE
                       WHEN issue_code = N'database-import-failure'
                           THEN N'Database import failed; inspect local logs'
                       ELSE issue_message
                   END AS message,
                   TRY_CONVERT(bigint, source_record_id) AS provider_match_id,
                   created_at_utc,
                   import_run_id,
                   source_snapshot_id
            FROM dbo.validation_issues
            ORDER BY created_at_utc DESC, validation_issue_id DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY;
            """,
            (offset, limit),
        )
        return items, int(total["total"])

    def notes(self, match_id: int) -> list[dict[str, Any]]:
        return self._read(
            """
            SELECT match_note_id AS note_id,
                   match_id,
                   note_text,
                   created_by,
                   is_archived,
                   created_at_utc,
                   updated_at_utc
            FROM dbo.match_notes
            WHERE match_id = ? AND is_archived = 0
            ORDER BY created_at_utc DESC, match_note_id DESC;
            """,
            (match_id,),
        )

    def create_note(self, match_id: int, note_text: str, created_by: str) -> dict[str, Any]:
        with closing(self._connection_factory()) as connection:
            try:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    INSERT INTO dbo.match_notes (match_id, note_text, created_by)
                    OUTPUT inserted.match_note_id AS note_id,
                           inserted.match_id,
                           inserted.note_text,
                           inserted.created_by,
                           inserted.is_archived,
                           inserted.created_at_utc,
                           inserted.updated_at_utc
                    VALUES (?, ?, ?);
                    """,
                    (match_id, note_text, created_by),
                )
                row = _rows(cursor)[0]
                connection.commit()
                return row
            except Exception:
                connection.rollback()
                raise

    def update_note(self, note_id: int, note_text: str) -> dict[str, Any] | None:
        with closing(self._connection_factory()) as connection:
            try:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    UPDATE dbo.match_notes
                    SET note_text = ?, updated_at_utc = SYSUTCDATETIME()
                    OUTPUT inserted.match_note_id AS note_id,
                           inserted.match_id,
                           inserted.note_text,
                           inserted.created_by,
                           inserted.is_archived,
                           inserted.created_at_utc,
                           inserted.updated_at_utc
                    WHERE match_note_id = ? AND is_archived = 0;
                    """,
                    (note_text, note_id),
                )
                rows = _rows(cursor)
                connection.commit()
                return rows[0] if rows else None
            except Exception:
                connection.rollback()
                raise

    def archive_note(self, note_id: int) -> bool:
        with closing(self._connection_factory()) as connection:
            try:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    UPDATE dbo.match_notes
                    SET is_archived = 1, updated_at_utc = SYSUTCDATETIME()
                    OUTPUT inserted.match_note_id
                    WHERE match_note_id = ? AND is_archived = 0;
                    """,
                    (note_id,),
                )
                changed = bool(_rows(cursor))
                connection.commit()
                return changed
            except Exception:
                connection.rollback()
                raise
