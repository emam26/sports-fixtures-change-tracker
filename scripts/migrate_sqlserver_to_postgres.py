"""Preview or apply a restart-safe SQL Server to PostgreSQL migration."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sports_tracker.config import (
    ConfigurationError,
    load_database_settings,
    load_postgresql_settings,
)
from sports_tracker.database import database_connection
from sports_tracker.postgres import postgresql_connection


class MigrationMismatchError(RuntimeError):
    """Raised when an existing PostgreSQL row differs from the SQL Server row."""


def _validated_schema(schema: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema) is None:
        raise MigrationMismatchError("PostgreSQL schema must be a simple SQL identifier")
    return schema


TABLE_SPECS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "competitions",
        "competition_id",
        (
            "competition_id",
            "provider",
            "provider_shortcut",
            "competition_name",
            "is_active",
            "created_at_utc",
            "updated_at_utc",
        ),
    ),
    (
        "competition_seasons",
        "competition_season_id",
        (
            "competition_season_id",
            "competition_id",
            "source_league_id",
            "season_start_year",
            "season_label",
            "created_at_utc",
        ),
    ),
    (
        "teams",
        "team_id",
        (
            "team_id",
            "provider",
            "provider_team_id",
            "team_name",
            "short_name",
            "tla",
            "team_group_name",
            "team_icon_url",
            "wikidata_id",
            "created_at_utc",
            "updated_at_utc",
        ),
    ),
    (
        "source_snapshots",
        "source_snapshot_id",
        (
            "source_snapshot_id",
            "provider",
            "provider_shortcut",
            "source_league_id",
            "season_start_year",
            "matchday_number",
            "competition_stage",
            "source_url",
            "retrieved_at_utc",
            "http_status",
            "content_type",
            "byte_count",
            "sha256",
            "local_directory",
            "response_path",
            "metadata_path",
            "created_at_utc",
        ),
    ),
    (
        "matches",
        "match_id",
        (
            "match_id",
            "competition_season_id",
            "provider",
            "provider_match_id",
            "home_team_id",
            "away_team_id",
            "matchday_number",
            "competition_stage",
            "source_group_id",
            "source_group_order_id",
            "source_group_name",
            "kickoff_utc",
            "source_match_is_finished",
            "source_last_update_utc",
            "source_last_update_raw",
            "source_time_zone_id",
            "location",
            "created_at_utc",
            "updated_at_utc",
        ),
    ),
    (
        "match_results",
        "match_result_id",
        (
            "match_result_id",
            "match_id",
            "provider",
            "provider_result_id",
            "result_type_id",
            "result_type_kind",
            "result_order_id",
            "result_name",
            "result_description",
            "points_team1",
            "points_team2",
            "created_at_utc",
        ),
    ),
    (
        "match_goals",
        "match_goal_id",
        (
            "match_goal_id",
            "match_id",
            "provider",
            "provider_goal_id",
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
            "created_at_utc",
        ),
    ),
    (
        "import_runs",
        "import_run_id",
        (
            "import_run_id",
            "provider",
            "competition_season_id",
            "source_snapshot_id",
            "matchday_number",
            "competition_stage",
            "requested_url",
            "started_at_utc",
            "completed_at_utc",
            "status",
            "is_replay",
            "replay_of_import_run_id",
            "matches_seen",
            "matches_inserted",
            "matches_updated",
            "matches_unchanged",
            "matches_rejected",
            "results_seen",
            "validation_issue_count",
            "failure_phase",
            "error_summary",
            "created_at_utc",
        ),
    ),
    (
        "validation_issues",
        "validation_issue_id",
        (
            "validation_issue_id",
            "import_run_id",
            "source_snapshot_id",
            "provider",
            "source_record_type",
            "source_record_id",
            "field_name",
            "issue_code",
            "severity",
            "issue_message",
            "source_value",
            "is_resolved",
            "created_at_utc",
        ),
    ),
    (
        "match_changes",
        "match_change_id",
        (
            "match_change_id",
            "match_id",
            "import_run_id",
            "source_snapshot_id",
            "field_name",
            "change_kind",
            "old_value",
            "new_value",
            "observed_at_utc",
            "source_last_update_utc",
            "created_at_utc",
        ),
    ),
    (
        "sync_checkpoints",
        "sync_checkpoint_id",
        (
            "sync_checkpoint_id",
            "provider",
            "competition_season_id",
            "scope_key",
            "matchday_number",
            "competition_stage",
            "last_successful_snapshot_id",
            "last_successful_import_run_id",
            "last_source_update_utc",
            "last_processed_at_utc",
            "updated_at_utc",
            "checkpoint_version",
        ),
    ),
    (
        "match_notes",
        "match_note_id",
        (
            "match_note_id",
            "match_id",
            "note_text",
            "created_by",
            "is_archived",
            "created_at_utc",
            "updated_at_utc",
        ),
    ),
)


def _utc_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC).isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return value


def stable_row_hash(rows: Iterable[Sequence[Any]]) -> str:
    """Hash normalized row values for an auditable source/target comparison."""

    encoded = [
        json.dumps([_utc_value(value) for value in row], separators=(",", ":")) for row in rows
    ]
    return hashlib.sha256("\n".join(encoded).encode("utf-8")).hexdigest()


def _target_columns(table: str, columns: tuple[str, ...]) -> tuple[str, ...]:
    if table != "sync_checkpoints":
        return columns
    return (*columns, "source_checkpoint_version")


def _target_values(table: str, columns: tuple[str, ...], row: Sequence[Any]) -> tuple[Any, ...]:
    values = list(row)
    if table == "sync_checkpoints":
        raw_version = values[columns.index("checkpoint_version")]
        values[columns.index("checkpoint_version")] = 1
        values.append(raw_version)
    return tuple(values)


def _fetch_source_rows(connection: Any, table: str, primary_key: str, columns: tuple[str, ...]):
    cursor = connection.cursor()
    quoted = ", ".join(f"[{column}]" for column in columns)
    cursor.execute(f"SELECT {quoted} FROM dbo.[{table}] ORDER BY [{primary_key}]")
    return cursor.fetchall()


def _fetch_target_row(
    connection: Any,
    table: str,
    primary_key: str,
    columns: tuple[str, ...],
    primary_value: Any,
    schema: str,
):
    cursor = connection.cursor()
    quoted = ", ".join(f'"{column}"' for column in columns)
    cursor.execute(
        f'SELECT {quoted} FROM "{schema}"."{table}" WHERE "{primary_key}" = %s',
        (primary_value,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    if isinstance(row, Mapping):
        return tuple(row[column] for column in columns)
    return tuple(row)


def _fetch_target_rows(
    connection: Any,
    table: str,
    primary_key: str,
    columns: tuple[str, ...],
    schema: str,
) -> list[tuple[Any, ...]]:
    cursor = connection.cursor()
    quoted = ", ".join(f'"{column}"' for column in columns)
    cursor.execute(f'SELECT {quoted} FROM "{schema}"."{table}" ORDER BY "{primary_key}"')
    rows = cursor.fetchall()
    if rows and isinstance(rows[0], Mapping):
        return [tuple(row[column] for column in columns) for row in rows]
    return [tuple(row) for row in rows]


def _insert_target_row(
    connection: Any,
    table: str,
    columns: tuple[str, ...],
    values: tuple[Any, ...],
    schema: str,
) -> None:
    column_sql = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join("%s" for _ in columns)
    connection.cursor().execute(
        f'INSERT INTO "{schema}"."{table}" ({column_sql}) VALUES ({placeholders})',
        values,
    )


def reconcile_and_migrate(*, apply: bool, schema: str = "public") -> dict[str, dict[str, Any]]:
    """Reconcile all rows and optionally insert only missing identical rows."""

    schema = _validated_schema(schema)
    report: dict[str, dict[str, Any]] = {}
    with database_connection(load_database_settings()) as source:
        with postgresql_connection(load_postgresql_settings()) as target:
            try:
                for table, primary_key, columns in TABLE_SPECS:
                    source_rows = _fetch_source_rows(source, table, primary_key, columns)
                    target_columns = _target_columns(table, columns)
                    target_rows = _fetch_target_rows(
                        target,
                        table,
                        primary_key,
                        target_columns,
                        schema,
                    )
                    target_by_id = {row[0]: row for row in target_rows}
                    inserted = 0
                    for source_row in source_rows:
                        values = _target_values(table, columns, source_row)
                        primary_value = source_row[columns.index(primary_key)]
                        target_row = target_by_id.get(primary_value)
                        if target_row is not None:
                            if stable_row_hash((target_row,)) != stable_row_hash((values,)):
                                raise MigrationMismatchError(
                                    f"target mismatch in {table}.{primary_key}={primary_value}"
                                )
                            continue
                        if apply:
                            _insert_target_row(target, table, target_columns, values, schema)
                            inserted += 1
                    source_ids = {row[columns.index(primary_key)] for row in source_rows}
                    extra_ids = sorted(set(target_by_id) - source_ids)
                    if extra_ids:
                        raise MigrationMismatchError(
                            f"target has rows absent from SQL Server in {table}."
                            f"{primary_key}: {extra_ids[:5]}"
                        )
                    report[table] = {
                        "source_count": len(source_rows),
                        "target_count": len(target_rows),
                        "inserted": inserted,
                        "source_hash": stable_row_hash(source_rows),
                    }
                if apply:
                    sequence_cursor = target.cursor()
                    for table, primary_key, _columns in TABLE_SPECS:
                        sequence_cursor.execute(
                            "SELECT setval(pg_get_serial_sequence(%s, %s), "
                            f'COALESCE((SELECT MAX("{primary_key}") '
                            f'FROM "{schema}"."{table}"), 1), '
                            f'(SELECT COUNT(*) > 0 FROM "{schema}"."{table}"))',
                            (f"{schema}.{table}", primary_key),
                        )
                    target.commit()
                else:
                    target.rollback()
            except Exception:
                target.rollback()
                raise
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply only rows absent from PostgreSQL after all comparisons pass",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_postgresql_settings()
        report = reconcile_and_migrate(apply=args.apply, schema=settings.schema)
    except (ConfigurationError, MigrationMismatchError, OSError, RuntimeError) as exc:
        print(f"Migration stopped safely: {type(exc).__name__}: {exc}")
        return 1
    mode = "applied" if args.apply else "previewed"
    print(f"Migration {mode}; source rows were not modified.")
    for table, details in report.items():
        print(
            f"{table}: source={details['source_count']} "
            f"target_before={details['target_count']} "
            f"inserted={details['inserted']} hash={details['source_hash']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
