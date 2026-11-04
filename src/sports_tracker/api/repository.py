"""Parameterized SQL Server queries used by the local API."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import closing
from typing import Any, Protocol


class Repository(Protocol):
    def health(self) -> None: ...

    def competitions(self) -> list[dict[str, Any]]: ...

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

    def match(self, match_id: int) -> dict[str, Any] | None: ...

    def changes(self, match_id: int) -> list[dict[str, Any]]: ...

    def import_runs(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]: ...

    def validation_issues(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]: ...

    def notes(self, match_id: int) -> list[dict[str, Any]]: ...

    def create_note(self, match_id: int, note_text: str, created_by: str) -> dict[str, Any]: ...

    def update_note(self, note_id: int, note_text: str) -> dict[str, Any] | None: ...

    def archive_note(self, note_id: int) -> bool: ...


def _rows(cursor: Any) -> list[dict[str, Any]]:
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


class SQLServerRepository:
    """Small query layer; each call owns and closes its connection."""

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory
        self._column_cache: dict[str, frozenset[str]] = {}

    def _read(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with closing(self._connection_factory()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, params)
            return _rows(cursor)

    def health(self) -> None:
        self._read("SELECT CAST(1 AS int) AS ready;")

    def _columns(self, table: str) -> frozenset[str]:
        cached = self._column_cache.get(table)
        if cached is not None:
            return cached
        rows = self._read(
            """
            SELECT c.name
            FROM sys.columns AS c
            INNER JOIN sys.tables AS t ON t.object_id = c.object_id
            INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
            WHERE s.name = 'dbo' AND t.name = ?;
            """,
            (table,),
        )
        columns = frozenset(str(row["name"]) for row in rows)
        if not columns:
            raise RuntimeError(f"Required table dbo.{table} was not found")
        self._column_cache[table] = columns
        return columns

    def _column(self, table: str, *allowed_names: str) -> str:
        available = self._columns(table)
        for name in allowed_names:
            if name in available:
                return f"[{name}]"
        choices = ", ".join(allowed_names)
        raise RuntimeError(f"dbo.{table} requires one of these columns: {choices}")

    def competitions(self) -> list[dict[str, Any]]:
        return self._read(
            """
            SELECT cs.competition_season_id, c.provider, c.name, c.shortcut,
                   cs.season, cs.provider_league_id
            FROM dbo.competition_seasons AS cs
            INNER JOIN dbo.competitions AS c
                ON c.competition_id = cs.competition_id
            ORDER BY cs.season DESC, c.name;
            """
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
        stage_column = self._column(
            "matches",
            "competition_stage",
            "stage_name",
            "group_name",
        )
        team_name = self._column("teams", "name", "team_name")
        source_update = self._column(
            "matches",
            "source_last_update_utc",
            "last_source_update_utc",
        )
        result_type = self._column("match_results", "result_type", "result_type_name")
        home_score = self._column(
            "match_results",
            "home_score",
            "points_home",
            "points_team1",
        )
        away_score = self._column(
            "match_results",
            "away_score",
            "points_away",
            "points_team2",
        )
        predicates = ["1 = 1"]
        params: list[Any] = []
        if competition_season_id is not None:
            predicates.append("m.competition_season_id = ?")
            params.append(competition_season_id)
        if matchday is not None:
            predicates.append("m.matchday_number = ?")
            params.append(matchday)
        if finished is not None:
            predicates.append("m.is_finished = ?")
            params.append(finished)
        if search:
            predicates.append(f"(ht.{team_name} LIKE ? OR at.{team_name} LIKE ?)")
            term = f"%{search}%"
            params.extend((term, term))
        where = " AND ".join(predicates)
        base = f"""
            FROM dbo.matches AS m
            INNER JOIN dbo.teams AS ht ON ht.team_id = m.home_team_id
            INNER JOIN dbo.teams AS at ON at.team_id = m.away_team_id
            OUTER APPLY (
                SELECT TOP (1) mr.{home_score} AS home_score,
                               mr.{away_score} AS away_score
                FROM dbo.match_results AS mr
                WHERE mr.match_id = m.match_id
                  AND mr.{result_type} = 'After90Minutes'
            ) AS final_result
            WHERE {where}
        """
        count = self._read(f"SELECT COUNT_BIG(*) AS total {base}", tuple(params))[0]
        page_params = (*params, offset, limit)
        items = self._read(
            f"""
            SELECT m.match_id, m.provider_match_id, m.matchday_number,
                   m.{stage_column} AS stage_name, m.kickoff_utc, m.is_finished,
                   ht.{team_name} AS home_team,
                   at.{team_name} AS away_team,
                   final_result.home_score, final_result.away_score,
                   m.{source_update} AS last_source_update_utc
            {base}
            ORDER BY m.kickoff_utc, m.match_id
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY;
            """,
            page_params,
        )
        return items, int(count["total"])

    def match(self, match_id: int) -> dict[str, Any] | None:
        stage_column = self._column(
            "matches",
            "competition_stage",
            "stage_name",
            "group_name",
        )
        venue_column = self._column("matches", "location", "venue")
        team_name = self._column("teams", "name", "team_name")
        source_update = self._column(
            "matches",
            "source_last_update_utc",
            "last_source_update_utc",
        )
        result_type = self._column("match_results", "result_type", "result_type_name")
        result_name = self._column(
            "match_results",
            "result_name",
            "result_description",
            "description",
        )
        home_score = self._column(
            "match_results",
            "home_score",
            "points_home",
            "points_team1",
        )
        away_score = self._column(
            "match_results",
            "away_score",
            "points_away",
            "points_team2",
        )
        result_order = self._column(
            "match_results",
            "result_order",
            "result_order_id",
            "order_id",
        )
        goal_id = self._column("match_goals", "provider_goal_id")
        goal_home = self._column(
            "match_goals",
            "score_home",
            "points_home",
            "score_team1",
        )
        goal_away = self._column(
            "match_goals",
            "score_away",
            "points_away",
            "score_team2",
        )
        goal_minute = self._column("match_goals", "minute", "match_minute")
        scorer = self._column("match_goals", "scorer_name", "goal_getter_name")
        penalty = self._column("match_goals", "is_penalty")
        own_goal = self._column("match_goals", "is_own_goal")
        overtime = self._column("match_goals", "is_overtime")
        goal_order = self._column(
            "match_goals",
            "goal_order",
            "goal_order_id",
            "order_id",
        )
        records = self._read(
            f"""
            SELECT m.match_id, m.provider_match_id, m.matchday_number,
                   m.{stage_column} AS stage_name, m.kickoff_utc, m.is_finished,
                   ht.{team_name} AS home_team,
                   at.{team_name} AS away_team,
                   final_result.home_score, final_result.away_score,
                   m.{source_update} AS last_source_update_utc,
                   m.{venue_column} AS venue
            FROM dbo.matches AS m
            INNER JOIN dbo.teams AS ht ON ht.team_id = m.home_team_id
            INNER JOIN dbo.teams AS at ON at.team_id = m.away_team_id
            OUTER APPLY (
                SELECT TOP (1) mr.{home_score} AS home_score,
                               mr.{away_score} AS away_score
                FROM dbo.match_results AS mr
                WHERE mr.match_id = m.match_id
                  AND mr.{result_type} = 'After90Minutes'
            ) AS final_result
            WHERE m.match_id = ?;
            """,
            (match_id,),
        )
        if not records:
            return None
        record = records[0]
        record["results"] = self._read(
            f"""
            SELECT {result_type} AS result_type, {result_name} AS result_name,
                   {home_score} AS home_score, {away_score} AS away_score
            FROM dbo.match_results
            WHERE match_id = ?
            ORDER BY {result_order}, match_result_id;
            """,
            (match_id,),
        )
        record["goals"] = self._read(
            f"""
            SELECT {goal_id} AS provider_goal_id,
                   {goal_home} AS score_home, {goal_away} AS score_away,
                   {goal_minute} AS minute, {scorer} AS scorer_name,
                   {penalty} AS is_penalty, {own_goal} AS is_own_goal,
                   {overtime} AS is_overtime
            FROM dbo.match_goals
            WHERE match_id = ?
            ORDER BY {goal_order}, match_goal_id;
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

    def import_runs(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        total = self._read("SELECT COUNT_BIG(*) AS total FROM dbo.import_runs;")[0]
        items = self._read(
            """
            SELECT ir.import_run_id, ir.status, ir.started_at_utc,
                   ir.completed_at_utc, ss.content_sha256 AS snapshot_sha256,
                   ir.matches_seen, ir.matches_inserted, ir.matches_updated,
                   ir.results_seen, ir.validation_issue_count, ir.error_message
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
            SELECT validation_issue_id, severity, issue_code, message,
                   provider_match_id, created_at_utc, import_run_id,
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
            SELECT note_id, match_id, note_text, created_by, is_archived,
                   created_at_utc, updated_at_utc
            FROM dbo.match_notes
            WHERE match_id = ? AND is_archived = 0
            ORDER BY created_at_utc DESC, note_id DESC;
            """,
            (match_id,),
        )

    def create_note(self, match_id: int, note_text: str, created_by: str) -> dict[str, Any]:
        with closing(self._connection_factory()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO dbo.match_notes (match_id, note_text, created_by)
                OUTPUT inserted.note_id, inserted.match_id, inserted.note_text,
                       inserted.created_by, inserted.is_archived,
                       inserted.created_at_utc, inserted.updated_at_utc
                VALUES (?, ?, ?);
                """,
                (match_id, note_text, created_by),
            )
            row = _rows(cursor)[0]
            connection.commit()
            return row

    def update_note(self, note_id: int, note_text: str) -> dict[str, Any] | None:
        with closing(self._connection_factory()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                UPDATE dbo.match_notes
                SET note_text = ?, updated_at_utc = SYSUTCDATETIME()
                OUTPUT inserted.note_id, inserted.match_id, inserted.note_text,
                       inserted.created_by, inserted.is_archived,
                       inserted.created_at_utc, inserted.updated_at_utc
                WHERE note_id = ? AND is_archived = 0;
                """,
                (note_text, note_id),
            )
            rows = _rows(cursor)
            connection.commit()
            return rows[0] if rows else None

    def archive_note(self, note_id: int) -> bool:
        with closing(self._connection_factory()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                UPDATE dbo.match_notes
                SET is_archived = 1, updated_at_utc = SYSUTCDATETIME()
                WHERE note_id = ? AND is_archived = 0;
                """,
                (note_id,),
            )
            changed = cursor.rowcount > 0
            connection.commit()
            return changed
