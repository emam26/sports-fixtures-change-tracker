"""PostgreSQL API repository using the same response contract as SQL Server."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from typing import Any

from .repository import MatchSort, _like_pattern


def _postgres_rows(cursor: Any) -> list[dict[str, Any]]:
    if cursor.description is None:
        return []
    names = [column.name if hasattr(column, "name") else column[0] for column in cursor.description]
    records: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        if isinstance(row, dict):
            record = dict(row)
        else:
            record = dict(zip(names, row, strict=True))
        for name, value in record.items():
            if name.endswith("_utc") and isinstance(value, datetime) and value.tzinfo is None:
                record[name] = value.replace(tzinfo=UTC)
        records.append(record)
    return records


class PostgreSQLRepository:
    """Small PostgreSQL query layer with parameterized SQL and owned connections."""

    def __init__(self, connection_factory: Callable[[], Any], schema: str = "public") -> None:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema) is None:
            raise ValueError("PostgreSQL schema must be a simple SQL identifier")
        self._connection_factory = connection_factory
        self._schema = schema

    def _table(self, name: str) -> str:
        return f'"{self._schema}"."{name}"'

    def _read(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with closing(self._connection_factory()) as connection:
            cursor = connection.cursor()
            cursor.execute(sql, params)
            return _postgres_rows(cursor)

    def _write(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with closing(self._connection_factory()) as connection:
            try:
                cursor = connection.cursor()
                cursor.execute(sql, params)
                rows = _postgres_rows(cursor)
                connection.commit()
                return rows
            except Exception:
                connection.rollback()
                raise

    def close(self) -> None:
        """Close a pool when the application owns one; direct factories need no action."""

        close = getattr(self._connection_factory, "close", None)
        if close is not None:
            close()

    def health(self) -> None:
        self._read("SELECT 1 AS ready")

    def competitions(self) -> list[dict[str, Any]]:
        c = self._table("competitions")
        cs = self._table("competition_seasons")
        return self._read(
            f"""
            SELECT cs.competition_season_id, c.provider,
                   c.competition_name AS name, c.provider_shortcut AS shortcut,
                   COALESCE(cs.season_label, cs.season_start_year::text) AS season,
                   cs.source_league_id AS provider_league_id
            FROM {cs} AS cs
            INNER JOIN {c} AS c ON c.competition_id = cs.competition_id
            WHERE c.is_active IS TRUE
            ORDER BY cs.season_start_year DESC, c.competition_name
            """
        )

    def matchdays(self, competition_season_id: int | None) -> list[dict[str, Any]]:
        m = self._table("matches")
        predicates = ["m.matchday_number IS NOT NULL"]
        params: list[Any] = []
        if competition_season_id is not None:
            predicates.append("m.competition_season_id = %s")
            params.append(competition_season_id)
        return self._read(
            f"""
            SELECT m.competition_season_id, m.matchday_number,
                   COUNT(*) AS match_count,
                   SUM(CASE WHEN m.source_match_is_finished THEN 1 ELSE 0 END)
                       AS finished_count,
                   SUM(CASE WHEN NOT m.source_match_is_finished THEN 1 ELSE 0 END)
                       AS unfinished_count,
                   MIN(m.kickoff_utc) AS first_kickoff_utc,
                   MAX(m.kickoff_utc) AS last_kickoff_utc
            FROM {m} AS m
            WHERE {" AND ".join(predicates)}
            GROUP BY m.competition_season_id, m.matchday_number
            ORDER BY m.competition_season_id, m.matchday_number
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
        sort: MatchSort = "explorer",
    ) -> tuple[list[dict[str, Any]], int]:
        m = self._table("matches")
        t = self._table("teams")
        r = self._table("match_results")
        predicates = ["TRUE"]
        params: list[Any] = []
        if competition_season_id is not None:
            predicates.append("m.competition_season_id = %s")
            params.append(competition_season_id)
        if matchday is not None:
            predicates.append("m.matchday_number = %s")
            params.append(matchday)
        if finished is not None:
            predicates.append("m.source_match_is_finished = %s")
            params.append(finished)
        if search:
            predicates.append(
                "(ht.team_name ILIKE %s ESCAPE '~' OR at.team_name ILIKE %s ESCAPE '~')"
            )
            term = _like_pattern(search)
            params.extend((term, term))
        where = " AND ".join(predicates)
        base = f"""
            FROM {m} AS m
            INNER JOIN {t} AS ht ON ht.team_id = m.home_team_id
            INNER JOIN {t} AS at ON at.team_id = m.away_team_id
            LEFT JOIN LATERAL (
                SELECT mr.points_team1 AS home_score,
                       mr.points_team2 AS away_score
                FROM {r} AS mr
                WHERE mr.match_id = m.match_id
                  AND mr.result_type_kind = 'After90Minutes'
                ORDER BY mr.result_order_id DESC NULLS LAST, mr.match_result_id DESC
                LIMIT 1
            ) AS final_result ON TRUE
            WHERE {where}
        """
        total = self._read(f"SELECT COUNT(*) AS total {base}", tuple(params))[0]
        if sort == "explorer" and finished is None:
            order = """
                CASE WHEN m.source_match_is_finished THEN 0 ELSE 1 END,
                CASE WHEN m.kickoff_utc IS NULL THEN 1 ELSE 0 END,
                CASE WHEN m.source_match_is_finished THEN m.kickoff_utc END DESC,
                CASE WHEN NOT m.source_match_is_finished THEN m.kickoff_utc END ASC,
                CASE WHEN m.source_match_is_finished THEN m.provider_match_id END DESC,
                CASE WHEN NOT m.source_match_is_finished THEN m.provider_match_id END ASC
            """
        else:
            direction = "DESC" if sort == "kickoff-desc" or finished is True else "ASC"
            order = (
                f"CASE WHEN m.kickoff_utc IS NULL THEN 1 ELSE 0 END, "
                f"m.kickoff_utc {direction}, m.provider_match_id {direction}"
            )
        items = self._read(
            f"""
            SELECT m.match_id, m.provider_match_id, m.matchday_number,
                   m.competition_stage AS stage_name, m.kickoff_utc,
                   m.source_match_is_finished AS is_finished,
                   ht.team_name AS home_team, at.team_name AS away_team,
                   final_result.home_score, final_result.away_score,
                   m.source_last_update_utc AS last_source_update_utc
            {base}
            ORDER BY {order}
            OFFSET %s LIMIT %s
            """,
            (*params, offset, limit),
        )
        return items, int(total["total"])

    def dashboard_summary(self, competition_season_id: int | None) -> dict[str, Any]:
        m = self._table("matches")
        g = self._table("match_goals")
        c = self._table("match_changes")
        sc = self._table("sync_checkpoints")
        match_filter = "TRUE" if competition_season_id is None else "m.competition_season_id = %s"
        checkpoint_filter = (
            "TRUE" if competition_season_id is None else "sc.competition_season_id = %s"
        )
        params: tuple[Any, ...] = () if competition_season_id is None else (competition_season_id,)
        fixture = self._read(
            f"""
            SELECT COUNT(*) AS total_fixtures,
                   COALESCE(SUM(CASE WHEN m.source_match_is_finished THEN 1 ELSE 0 END), 0)
                       AS finished_fixtures,
                   COALESCE(SUM(CASE WHEN NOT m.source_match_is_finished THEN 1 ELSE 0 END), 0)
                       AS upcoming_fixtures
            FROM {m} AS m WHERE {match_filter}
            """,
            params,
        )[0]
        goals = self._read(
            f"SELECT COUNT(*) AS goals_recorded FROM {g} AS mg "
            f"INNER JOIN {m} AS m ON m.match_id = mg.match_id WHERE {match_filter}",
            params,
        )[0]
        changes = self._read(
            f"""
            SELECT COUNT(*) AS detected_changes,
                   COUNT(DISTINCT mc.match_id) AS changed_fixtures
            FROM {c} AS mc INNER JOIN {m} AS m ON m.match_id = mc.match_id
            WHERE {match_filter}
            """,
            params,
        )[0]
        checkpoint = self._read(
            f"""
            SELECT sc.last_processed_at_utc AS latest_successful_sync_at_utc,
                   sc.last_successful_snapshot_id, sc.last_successful_import_run_id
            FROM {sc} AS sc
            WHERE sc.last_successful_import_run_id IS NOT NULL
              AND sc.last_processed_at_utc IS NOT NULL
              AND {checkpoint_filter}
            ORDER BY sc.last_processed_at_utc DESC, sc.sync_checkpoint_id DESC
            LIMIT 1
            """,
            params,
        )
        latest = checkpoint[0] if checkpoint else {}
        return {
            "total_fixtures": int(fixture["total_fixtures"] or 0),
            "finished_fixtures": int(fixture["finished_fixtures"] or 0),
            "upcoming_fixtures": int(fixture["upcoming_fixtures"] or 0),
            "goals_recorded": int(goals["goals_recorded"] or 0),
            "detected_changes": int(changes["detected_changes"] or 0),
            "changed_fixtures": int(changes["changed_fixtures"] or 0),
            "latest_successful_sync_at_utc": latest.get("latest_successful_sync_at_utc"),
            "latest_successful_snapshot_id": latest.get("last_successful_snapshot_id"),
            "latest_successful_import_run_id": latest.get("last_successful_import_run_id"),
        }

    def freshness(self, competition_season_id: int | None) -> dict[str, Any]:
        sc = self._table("sync_checkpoints")
        ss = self._table("source_snapshots")
        predicates = [
            "sc.last_successful_import_run_id IS NOT NULL",
            "sc.last_processed_at_utc IS NOT NULL",
        ]
        params: list[Any] = []
        if competition_season_id is not None:
            predicates.append("sc.competition_season_id = %s")
            params.append(competition_season_id)
        records = self._read(
            f"""
            SELECT sc.last_processed_at_utc AS latest_successful_sync_at_utc,
                   sc.last_successful_snapshot_id, sc.last_successful_import_run_id,
                   ss.sha256 AS source_snapshot_sha256
            FROM {sc} AS sc
            LEFT JOIN {ss} AS ss ON ss.source_snapshot_id = sc.last_successful_snapshot_id
            WHERE {" AND ".join(predicates)}
            ORDER BY sc.last_processed_at_utc DESC, sc.sync_checkpoint_id DESC
            LIMIT 1
            """,
            tuple(params),
        )
        if not records:
            return {"revision": None, "latest_successful_sync_at_utc": None}
        record = records[0]
        timestamp = record.get("latest_successful_sync_at_utc")
        snapshot_id = record.get("last_successful_snapshot_id")
        import_run_id = record.get("last_successful_import_run_id")
        snapshot_sha256 = record.get("source_snapshot_sha256")
        if snapshot_sha256:
            material = f"{snapshot_sha256}|{competition_season_id or ''}"
        elif timestamp is None or snapshot_id is None or import_run_id is None:
            return {"revision": None, "latest_successful_sync_at_utc": timestamp}
        else:
            material = f"{timestamp.isoformat()}|{snapshot_id}|{import_run_id}"
        return {
            "revision": hashlib.sha256(material.encode("utf-8")).hexdigest(),
            "latest_successful_sync_at_utc": timestamp,
        }

    def insight_rows(self, competition_season_id: int | None) -> list[dict[str, Any]]:
        m = self._table("matches")
        t = self._table("teams")
        r = self._table("match_results")
        g = self._table("match_goals")
        predicates = ["TRUE"]
        params: list[Any] = []
        if competition_season_id is not None:
            predicates.append("m.competition_season_id = %s")
            params.append(competition_season_id)
        return self._read(
            f"""
            WITH goal_counts AS (
                SELECT match_id, COUNT(*) AS observed_goal_events
                FROM {g} GROUP BY match_id
            ), final_results AS (
                SELECT DISTINCT ON (match_id) match_id,
                       points_team1 AS home_score, points_team2 AS away_score
                FROM {r}
                WHERE result_type_kind = 'After90Minutes'
                ORDER BY match_id, result_order_id DESC NULLS LAST, match_result_id DESC
            )
            SELECT m.match_id, m.provider_match_id, m.matchday_number, m.kickoff_utc,
                   m.source_match_is_finished AS is_finished,
                   ht.provider_team_id AS home_team_provider_id,
                   at.provider_team_id AS away_team_provider_id,
                   ht.team_name AS home_team, at.team_name AS away_team,
                   fr.home_score, fr.away_score,
                   COALESCE(gc.observed_goal_events, 0) AS observed_goal_events
            FROM {m} AS m
            INNER JOIN {t} AS ht ON ht.team_id = m.home_team_id
            INNER JOIN {t} AS at ON at.team_id = m.away_team_id
            LEFT JOIN final_results AS fr ON fr.match_id = m.match_id
            LEFT JOIN goal_counts AS gc ON gc.match_id = m.match_id
            WHERE {" AND ".join(predicates)}
            ORDER BY m.kickoff_utc NULLS LAST, m.match_id
            """,
            tuple(params),
        )

    def insight_latest_successful_sync(self, competition_season_id: int | None) -> datetime | None:
        result = self.freshness(competition_season_id)
        return result["latest_successful_sync_at_utc"]

    def match(self, match_id: int) -> dict[str, Any] | None:
        m = self._table("matches")
        t = self._table("teams")
        r = self._table("match_results")
        g = self._table("match_goals")
        records = self._read(
            f"""
            WITH final_results AS (
                SELECT DISTINCT ON (match_id) match_id,
                       points_team1 AS home_score, points_team2 AS away_score
                FROM {r}
                WHERE result_type_kind = 'After90Minutes'
                ORDER BY match_id, result_order_id DESC NULLS LAST, match_result_id DESC
            )
            SELECT m.match_id, m.provider_match_id, m.matchday_number,
                   m.competition_stage AS stage_name, m.kickoff_utc,
                   m.source_match_is_finished AS is_finished,
                   ht.team_name AS home_team, at.team_name AS away_team,
                   fr.home_score, fr.away_score,
                   m.source_last_update_utc AS last_source_update_utc,
                   m.location AS venue
            FROM {m} AS m
            INNER JOIN {t} AS ht ON ht.team_id = m.home_team_id
            INNER JOIN {t} AS at ON at.team_id = m.away_team_id
            LEFT JOIN final_results AS fr ON fr.match_id = m.match_id
            WHERE m.match_id = %s
            """,
            (match_id,),
        )
        if not records:
            return None
        record = records[0]
        record["results"] = self._read(
            f"""
            SELECT result_type_kind AS result_type,
                   COALESCE(result_name, result_description) AS result_name,
                   points_team1 AS home_score, points_team2 AS away_score
            FROM {r} WHERE match_id = %s
            ORDER BY result_order_id NULLS LAST, match_result_id
            """,
            (match_id,),
        )
        record["goals"] = self._read(
            f"""
            SELECT provider_goal_id, score_team1 AS score_home,
                   score_team2 AS score_away, match_minute AS minute,
                   goal_getter_name AS scorer_name, is_penalty, is_own_goal, is_overtime
            FROM {g} WHERE match_id = %s
            ORDER BY match_minute NULLS LAST, provider_goal_id, match_goal_id
            """,
            (match_id,),
        )
        return record

    def changes(self, match_id: int) -> list[dict[str, Any]]:
        c = self._table("match_changes")
        return self._read(
            f"""
            SELECT match_change_id, field_name, change_kind, old_value, new_value,
                   observed_at_utc, source_last_update_utc, import_run_id, source_snapshot_id
            FROM {c} WHERE match_id = %s
            ORDER BY observed_at_utc DESC, match_change_id DESC
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
        c, m, t, ss = (
            self._table(name) for name in ("match_changes", "matches", "teams", "source_snapshots")
        )
        predicates = ["TRUE"]
        params: list[Any] = []
        if competition_season_id is not None:
            predicates.append("m.competition_season_id = %s")
            params.append(competition_season_id)
        base = f"""
            FROM {c} AS mc
            INNER JOIN {m} AS m ON m.match_id = mc.match_id
            INNER JOIN {t} AS ht ON ht.team_id = m.home_team_id
            INNER JOIN {t} AS at ON at.team_id = m.away_team_id
            INNER JOIN {ss} AS ss ON ss.source_snapshot_id = mc.source_snapshot_id
            WHERE {" AND ".join(predicates)}
        """
        total = self._read(f"SELECT COUNT(*) AS total {base}", tuple(params))[0]
        items = self._read(
            f"""
            SELECT mc.match_change_id, m.match_id, m.provider_match_id, m.matchday_number,
                   ht.team_name AS home_team, at.team_name AS away_team,
                   mc.field_name, mc.change_kind, mc.old_value, mc.new_value,
                   mc.observed_at_utc, mc.source_last_update_utc, mc.import_run_id,
                   mc.source_snapshot_id, ss.sha256 AS snapshot_sha256,
                   ss.retrieved_at_utc AS snapshot_retrieved_at_utc
            {base}
            ORDER BY mc.observed_at_utc DESC, mc.match_change_id DESC
            OFFSET %s LIMIT %s
            """,
            (*params, offset, limit),
        )
        return items, int(total["total"])

    def _paged_table(
        self,
        table: str,
        columns: str,
        order: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        name = self._table(table)
        total = self._read(f"SELECT COUNT(*) AS total FROM {name}")[0]
        items = self._read(
            f"SELECT {columns} FROM {name} ORDER BY {order} OFFSET %s LIMIT %s",
            (offset, limit),
        )
        return items, int(total["total"])

    def sync_checkpoints(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        return self._paged_table(
            "sync_checkpoints",
            "sync_checkpoint_id, provider, scope_key, matchday_number, "
            "last_source_update_utc, last_processed_at_utc, "
            "last_successful_snapshot_id, last_successful_import_run_id",
            "updated_at_utc DESC, sync_checkpoint_id DESC",
            limit,
            offset,
        )

    def import_runs(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        ir, ss = self._table("import_runs"), self._table("source_snapshots")
        total = self._read(f"SELECT COUNT(*) AS total FROM {ir}")[0]
        items = self._read(
            f"""
            SELECT ir.import_run_id, ir.status, ir.started_at_utc, ir.completed_at_utc,
                   ss.sha256 AS snapshot_sha256, ir.matchday_number, ir.is_replay,
                   ir.matches_seen, ir.matches_inserted, ir.matches_updated,
                   ir.matches_unchanged, ir.matches_rejected, ir.results_seen,
                   ir.validation_issue_count, ir.failure_phase,
                   CASE WHEN ir.error_summary IS NULL THEN NULL
                        ELSE COALESCE(ir.failure_phase, 'import') || ' failure; inspect local logs'
                   END AS error_message
            FROM {ir} AS ir LEFT JOIN {ss} AS ss
              ON ss.source_snapshot_id = ir.source_snapshot_id
            ORDER BY ir.started_at_utc DESC, ir.import_run_id DESC
            OFFSET %s LIMIT %s
            """,
            (offset, limit),
        )
        return items, int(total["total"])

    def validation_issues(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        vi = self._table("validation_issues")
        total = self._read(f"SELECT COUNT(*) AS total FROM {vi}")[0]
        items = self._read(
            f"""
            SELECT validation_issue_id, severity, issue_code, issue_message AS message,
                   CASE WHEN source_record_id ~ '^[0-9]+$'
                        THEN source_record_id::bigint ELSE NULL END AS provider_match_id,
                   created_at_utc, import_run_id, source_snapshot_id
            FROM {vi}
            ORDER BY created_at_utc DESC, validation_issue_id DESC
            OFFSET %s LIMIT %s
            """,
            (offset, limit),
        )
        return items, int(total["total"])

    def notes(self, match_id: int) -> list[dict[str, Any]]:
        n = self._table("match_notes")
        return self._read(
            f"""
            SELECT match_note_id AS note_id, match_id, note_text, created_by,
                   is_archived, created_at_utc, updated_at_utc
            FROM {n} WHERE match_id = %s AND is_archived IS FALSE
            ORDER BY created_at_utc DESC, match_note_id DESC
            """,
            (match_id,),
        )

    def create_note(self, match_id: int, note_text: str, created_by: str) -> dict[str, Any]:
        n = self._table("match_notes")
        return self._write(
            f"""
            INSERT INTO {n} (match_id, note_text, created_by)
            VALUES (%s, %s, %s)
            RETURNING match_note_id AS note_id, match_id, note_text, created_by,
                      is_archived, created_at_utc, updated_at_utc
            """,
            (match_id, note_text, created_by),
        )[0]

    def update_note(self, note_id: int, note_text: str) -> dict[str, Any] | None:
        n = self._table("match_notes")
        rows = self._write(
            f"""
            UPDATE {n}
            SET note_text = %s, updated_at_utc = CURRENT_TIMESTAMP
            WHERE match_note_id = %s AND is_archived IS FALSE
            RETURNING match_note_id AS note_id, match_id, note_text, created_by,
                      is_archived, created_at_utc, updated_at_utc
            """,
            (note_text, note_id),
        )
        return rows[0] if rows else None

    def archive_note(self, note_id: int) -> bool:
        n = self._table("match_notes")
        return bool(
            self._write(
                f"""
                UPDATE {n} SET is_archived = TRUE, updated_at_utc = CURRENT_TIMESTAMP
                WHERE match_note_id = %s AND is_archived IS FALSE
                RETURNING match_note_id
                """,
                (note_id,),
            )
        )
