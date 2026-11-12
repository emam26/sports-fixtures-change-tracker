"""Read-only parity reporting for the SQL Server to PostgreSQL migration."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

TABLE_NAMES = (
    "competitions",
    "competition_seasons",
    "teams",
    "source_snapshots",
    "matches",
    "match_results",
    "match_goals",
    "match_changes",
    "import_runs",
    "validation_issues",
    "sync_checkpoints",
    "match_notes",
)

TIMESTAMP_POLICY = (
    "Documented *_utc values treat naive SQL Server datetimes as UTC. "
    "Datetime values are normalized to UTC and compared at Python microsecond precision. "
    "SQL Server datetime2(7) sub-microsecond precision is not representable by this report "
    "and must not be treated as independently verified."
)

PARITY_STATUSES = ("MATCH", "MISMATCH", "MISSING", "NOT CHECKED", "ERROR")

SYNC_CHECKPOINT_ROWVERSION_COLUMN = "checkpoint_version"
SYNC_CHECKPOINT_SOURCE_ROWVERSION_COLUMN = "source_checkpoint_version"

UTC_DATETIME_COLUMNS = frozenset(
    {
        "kickoff_utc",
        "retrieved_at_utc",
        "captured_at_utc",
        "created_at_utc",
        "updated_at_utc",
        "started_at_utc",
        "completed_at_utc",
        "changed_at_utc",
        "imported_at_utc",
        "expires_at_utc",
        "last_seen_at_utc",
    }
)

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_KEY_CANDIDATES = {
    "competitions": ("competition_id", "provider_competition_id"),
    "competition_seasons": ("competition_season_id", "provider_season_id"),
    "teams": ("team_id", "provider_team_id"),
    "source_snapshots": ("source_snapshot_id", "sha256"),
    "matches": ("match_id", "provider_match_id", "matchid"),
    "match_results": ("match_result_id", "provider_result_id", "result_id"),
    "match_goals": ("match_goal_id", "provider_goal_id", "goal_id"),
    "match_changes": ("match_change_id",),
    "import_runs": ("import_run_id",),
    "validation_issues": ("validation_issue_id",),
    "sync_checkpoints": ("sync_checkpoint_id",),
    "match_notes": ("match_note_id",),
}

_RELATIONSHIPS = {
    "competition_seasons": (("competition_id", "competitions"),),
    "matches": (
        ("competition_season_id", "competition_seasons"),
        ("home_team_id", "teams"),
        ("away_team_id", "teams"),
    ),
    "match_results": (("match_id", "matches"),),
    "match_goals": (("match_id", "matches"), ("scoring_team_id", "teams")),
    "match_changes": (
        ("match_id", "matches"),
        ("import_run_id", "import_runs"),
        ("source_snapshot_id", "source_snapshots"),
    ),
    "import_runs": (
        ("competition_season_id", "competition_seasons"),
        ("source_snapshot_id", "source_snapshots"),
        ("replayed_import_run_id", "import_runs"),
    ),
    "validation_issues": (
        ("import_run_id", "import_runs"),
        ("source_snapshot_id", "source_snapshots"),
    ),
    "sync_checkpoints": (
        ("competition_season_id", "competition_seasons"),
        ("source_snapshot_id", "source_snapshots"),
        ("import_run_id", "import_runs"),
    ),
    "match_notes": (("match_id", "matches"),),
}


def _validate_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid SQL identifier: {value!r}")
    return value


def _lookup(row: Mapping[str, Any], name: str) -> Any:
    wanted = name.casefold()
    for key, value in row.items():
        if str(key).casefold() == wanted:
            return value
    return None


def _normalize(value: Any, *, column_name: str | None = None) -> Any:
    """Canonicalize values without hiding documented transformation differences.

    Naive values in documented ``*_utc`` columns are SQL Server UTC values.
    Datetimes are compared at Python microsecond precision; SQL Server
    sub-microsecond precision is not independently verified.
    """
    if isinstance(value, datetime):
        column = column_name.casefold() if column_name is not None else None
        if column in UTC_DATETIME_COLUMNS or (column is not None and column.endswith("_utc")):
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            return value.astimezone(UTC).isoformat(timespec="microseconds")
        if value.tzinfo is None:
            return {
                "datetime": value.isoformat(timespec="microseconds"),
                "timezone": "naive",
            }
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"bytes_hex": bytes(value).hex()}
    if isinstance(value, Decimal):
        return {"decimal": str(value)}
    if isinstance(value, Mapping):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def _canonical(value: Any, *, column_name: str | None = None) -> str:
    return json.dumps(
        _normalize(value, column_name=column_name),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _row_key(table: str, row: Mapping[str, Any]) -> str:
    for candidate in _KEY_CANDIDATES.get(table, ()):
        value = _lookup(row, candidate)
        if value is not None:
            return f"{candidate}={_canonical(value)}"
    return f"row={_canonical(row)}"


def _as_mapping(columns: tuple[str, ...], row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return {str(key): value for key, value in row.items()}
    return dict(zip(columns, row, strict=False))


def read_table(
    connection: Any,
    schema: str,
    table: str,
) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    """Read one table without modifying the connection or database."""

    qualified = f"{_validate_identifier(schema)}.{_validate_identifier(table)}"
    cursor = connection.cursor()
    try:
        cursor.execute(f"SELECT * FROM {qualified}")
        columns = tuple(str(description[0]) for description in (cursor.description or ()))
        return columns, [_as_mapping(columns, row) for row in cursor.fetchall()]
    finally:
        close = getattr(cursor, "close", None)
        if close is not None:
            close()


def _keyed(table: str, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_row_key(table, row): row for row in rows}


def _duplicate_keys(table: str, rows: list[dict[str, Any]]) -> list[str]:
    counts = Counter(_row_key(table, row) for row in rows)
    return sorted(key for key, count in counts.items() if count > 1)


def _is_valid_application_checkpoint_version(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        integer_value = int(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return integer_value >= 0 and integer_value == value


def _legacy_compare_table(
    table: str,
    source_columns: tuple[str, ...],
    source_rows: list[dict[str, Any]],
    target_columns: tuple[str, ...],
    target_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare rows and return a deterministic, bounded diagnostic report."""

    source_by_key = _keyed(table, source_rows)
    target_by_key = _keyed(table, target_rows)
    source_duplicate_keys = _duplicate_keys(table, source_rows)
    target_duplicate_keys = _duplicate_keys(table, target_rows)
    source_only = sorted(set(source_by_key) - set(target_by_key))
    target_only = sorted(set(target_by_key) - set(source_by_key))
    source_column_map = {column.casefold(): column for column in source_columns}
    target_column_map = {column.casefold(): column for column in target_columns}
    common_columns = tuple(
        source_column_map[name] for name in sorted(set(source_column_map) & set(target_column_map))
    )
    checkpoint_mapping = table == "sync_checkpoints"
    source_has_rowversion = SYNC_CHECKPOINT_ROWVERSION_COLUMN.casefold() in source_column_map
    target_has_source_rowversion = (
        SYNC_CHECKPOINT_SOURCE_ROWVERSION_COLUMN.casefold() in target_column_map
    )
    target_has_application_version = (
        SYNC_CHECKPOINT_ROWVERSION_COLUMN.casefold() in target_column_map
    )
    mapping_errors: list[str] = []
    if checkpoint_mapping:
        if not source_has_rowversion:
            mapping_errors.append("source sync_checkpoints.checkpoint_version is missing")
        if not target_has_source_rowversion:
            mapping_errors.append("target sync_checkpoints.source_checkpoint_version is missing")
        if not target_has_application_version:
            mapping_errors.append("target sync_checkpoints.checkpoint_version is missing")

    differences: list[dict[str, Any]] = []
    for key in sorted(set(source_by_key) & set(target_by_key)):
        source = source_by_key[key]
        target = target_by_key[key]
        changed = {
            column: {
                "source": _normalize(_lookup(source, column), column_name=column),
                "target": _normalize(
                    _lookup(target, target_column_map[column.casefold()]),
                    column_name=target_column_map[column.casefold()],
                ),
            }
            for column in common_columns
            if _canonical(_lookup(source, column), column_name=column)
            != _canonical(
                _lookup(target, target_column_map[column.casefold()]),
                column_name=target_column_map[column.casefold()],
            )
        }
        if changed and len(differences) < 100:
            differences.append({"key": key, "fields": changed})

    schema_difference = sorted(
        set(source_column_map) ^ set(target_column_map),
    )
    if source_only or target_only:
        status = "MISSING"
    elif differences or schema_difference or source_duplicate_keys or target_duplicate_keys:
        status = "MISMATCH"
    else:
        status = "MATCH"
    return {
        "status": status,
        "source_count": len(source_rows),
        "target_count": len(target_rows),
        "source_only_keys": source_only[:100],
        "target_only_keys": target_only[:100],
        "source_duplicate_keys": source_duplicate_keys[:100],
        "target_duplicate_keys": target_duplicate_keys[:100],
        "row_differences": differences,
        "schema_difference": schema_difference,
        "source_columns": list(source_columns),
        "target_columns": list(target_columns),
    }


def _foreign_key_report(rows_by_table: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    key_sets = {table: set(_keyed(table, rows)) for table, rows in rows_by_table.items()}
    violations: list[dict[str, str]] = []
    for table, relationships in _RELATIONSHIPS.items():
        for child_column, parent_table in relationships:
            for row in rows_by_table.get(table, []):
                value = _lookup(row, child_column)
                if value is None or parent_table not in key_sets:
                    continue
                parent_key = None
                for key in key_sets[parent_table]:
                    if key.endswith(f"={_canonical(value)}"):
                        parent_key = key
                        break
                if parent_key is None:
                    violations.append(
                        {
                            "table": table,
                            "column": child_column,
                            "value": str(value),
                            "parent_table": parent_table,
                        }
                    )
    return {
        "status": "MATCH" if not violations else "MISMATCH",
        "violations": violations[:100],
    }


def _semantic_summary(rows_by_table: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    matches = rows_by_table.get("matches", [])
    snapshots = rows_by_table.get("source_snapshots", [])
    issues = rows_by_table.get("validation_issues", [])
    provider_ids = sorted(
        str(value) for row in matches if (value := _lookup(row, "provider_match_id")) is not None
    )
    snapshot_hashes = sorted(
        str(value) for row in snapshots if (value := _lookup(row, "sha256")) is not None
    )
    conflict_issues = sum(
        _lookup(row, "issue_code") == "conflicting-nonfinal-result-quarantined" for row in issues
    )
    return {
        "table_counts": {table: len(rows) for table, rows in sorted(rows_by_table.items())},
        "provider_match_ids": provider_ids,
        "snapshot_sha256": snapshot_hashes,
        "snapshot_timestamps": sorted(
            str(value)
            for row in snapshots
            for column in ("retrieved_at_utc", "retrieval_utc", "created_at_utc")
            if (value := _lookup(row, column)) is not None
        ),
        "quarantined_conflict_issues": conflict_issues,
        "match_statuses": sorted(
            str(value) for row in matches if (value := _lookup(row, "status")) is not None
        ),
        "result_types": sorted(
            str(value)
            for row in rows_by_table.get("match_results", [])
            if (value := _lookup(row, "result_type")) is not None
        ),
        "scores": [
            {
                "match_id": _normalize(_lookup(row, "match_id")),
                "home": _normalize(_lookup(row, "home_score")),
                "away": _normalize(_lookup(row, "away_score")),
                "result_type": _normalize(_lookup(row, "result_type")),
            }
            for row in rows_by_table.get("match_results", [])
        ],
        "goal_records": [
            {
                "match_id": _normalize(_lookup(row, "match_id")),
                "provider_goal_id": _normalize(_lookup(row, "provider_goal_id")),
                "minute": _normalize(_lookup(row, "minute")),
            }
            for row in rows_by_table.get("match_goals", [])
        ],
        "import_statuses": sorted(
            str(value)
            for row in rows_by_table.get("import_runs", [])
            if (value := _lookup(row, "status")) is not None
        ),
        "checkpoint_keys": sorted(
            _row_key("sync_checkpoints", row) for row in rows_by_table.get("sync_checkpoints", [])
        ),
    }


def compare_table(
    table: str,
    source_columns: Sequence[str],
    source_rows: Sequence[Mapping[str, Any]],
    target_columns: Sequence[str],
    target_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    source_by_key = _keyed(table, source_rows)
    target_by_key = _keyed(table, target_rows)
    source_duplicate_keys = _duplicate_keys(table, source_rows)
    target_duplicate_keys = _duplicate_keys(table, target_rows)
    source_column_map = {column.casefold(): column for column in source_columns}
    target_column_map = {column.casefold(): column for column in target_columns}
    source_names = set(source_column_map)
    target_names = set(target_column_map)
    checkpoint_mapping = table == "sync_checkpoints"
    mapping_errors: list[str] = []
    invariant_violations: list[str] = []
    excluded_source_columns: set[str] = set()
    excluded_target_columns: set[str] = set()

    if checkpoint_mapping:
        source_has_rowversion = SYNC_CHECKPOINT_ROWVERSION_COLUMN in source_names
        target_has_source_rowversion = SYNC_CHECKPOINT_SOURCE_ROWVERSION_COLUMN in target_names
        target_has_application_version = SYNC_CHECKPOINT_ROWVERSION_COLUMN in target_names
        if not source_has_rowversion:
            mapping_errors.append("source sync_checkpoints.checkpoint_version is missing")
        if not target_has_source_rowversion:
            mapping_errors.append("target sync_checkpoints.source_checkpoint_version is missing")
        if not target_has_application_version:
            mapping_errors.append("target sync_checkpoints.checkpoint_version is missing")
        excluded_source_columns.add(SYNC_CHECKPOINT_ROWVERSION_COLUMN)
        excluded_target_columns.update(
            {
                SYNC_CHECKPOINT_ROWVERSION_COLUMN,
                SYNC_CHECKPOINT_SOURCE_ROWVERSION_COLUMN,
            }
        )
    else:
        source_has_rowversion = False
        target_has_source_rowversion = False

    common_columns = tuple(
        source_column_map[name]
        for name in sorted(
            (source_names - excluded_source_columns) & (target_names - excluded_target_columns)
        )
    )
    differences: list[dict[str, Any]] = []
    for key in sorted(set(source_by_key) & set(target_by_key)):
        source = source_by_key[key]
        target = target_by_key[key]
        changed: dict[str, Any] = {}
        for column in common_columns:
            target_column = target_column_map[column.casefold()]
            source_value = _lookup(source, column)
            target_value = _lookup(target, target_column)
            if _canonical(source_value, column_name=column) != _canonical(
                target_value, column_name=target_column
            ):
                changed[column] = {
                    "source": _normalize(source_value, column_name=column),
                    "target": _normalize(target_value, column_name=target_column),
                }

        if checkpoint_mapping:
            source_rowversion = _lookup(source, SYNC_CHECKPOINT_ROWVERSION_COLUMN)
            target_rowversion = _lookup(target, SYNC_CHECKPOINT_SOURCE_ROWVERSION_COLUMN)
            if (
                source_has_rowversion
                and target_has_source_rowversion
                and (
                    _canonical(
                        source_rowversion,
                        column_name=SYNC_CHECKPOINT_ROWVERSION_COLUMN,
                    )
                    != _canonical(
                        target_rowversion,
                        column_name=SYNC_CHECKPOINT_SOURCE_ROWVERSION_COLUMN,
                    )
                )
            ):
                changed["checkpoint_version -> source_checkpoint_version"] = {
                    "source": _normalize(
                        source_rowversion,
                        column_name=SYNC_CHECKPOINT_ROWVERSION_COLUMN,
                    ),
                    "target": _normalize(
                        target_rowversion,
                        column_name=SYNC_CHECKPOINT_SOURCE_ROWVERSION_COLUMN,
                    ),
                }

            application_version = _lookup(target, SYNC_CHECKPOINT_ROWVERSION_COLUMN)
            if not _is_valid_application_checkpoint_version(application_version):
                invariant_violations.append(
                    f"{key}: target checkpoint_version must be a non-negative integer"
                )
                changed["checkpoint_version (application invariant)"] = {
                    "target": _normalize(
                        application_version,
                        column_name=SYNC_CHECKPOINT_ROWVERSION_COLUMN,
                    ),
                    "expected": "non-negative integer",
                }

        if changed:
            differences.append({"key": key, "changes": changed})

    source_only = sorted(set(source_by_key) - set(target_by_key))
    target_only = sorted(set(target_by_key) - set(source_by_key))
    if checkpoint_mapping:
        schema_difference = sorted(
            (source_names - excluded_source_columns) ^ (target_names - excluded_target_columns)
        )
        schema_difference.extend(mapping_errors)
    else:
        schema_difference = sorted(source_names ^ target_names)

    if source_only or target_only:
        status = "MISSING"
    elif differences or schema_difference or source_duplicate_keys or target_duplicate_keys:
        status = "MISMATCH"
    else:
        status = "MATCH"

    return {
        "table": table,
        "status": status,
        "source_count": len(source_rows),
        "target_count": len(target_rows),
        "source_only_keys": source_only,
        "target_only_keys": target_only,
        "source_duplicate_keys": source_duplicate_keys,
        "target_duplicate_keys": target_duplicate_keys,
        "row_differences": differences,
        "schema_difference": schema_difference,
        "source_columns": list(source_columns),
        "target_columns": list(target_columns),
        "transformation_mapping": (
            ["sync_checkpoints.checkpoint_version -> sync_checkpoints.source_checkpoint_version"]
            if checkpoint_mapping
            else []
        ),
        "application_invariant_violations": invariant_violations,
    }


def build_parity_report(
    source_connection: Any,
    target_connection: Any,
    *,
    source_schema: str = "dbo",
    target_schema: str = "public",
) -> dict[str, Any]:
    """Build a read-only parity report for all migrated domain tables."""

    source_data: dict[str, tuple[tuple[str, ...], list[dict[str, Any]]]] = {}
    target_data: dict[str, tuple[tuple[str, ...], list[dict[str, Any]]]] = {}
    table_reports: dict[str, dict[str, Any]] = {}
    for table in TABLE_NAMES:
        source_error = target_error = None
        try:
            source_data[table] = read_table(source_connection, source_schema, table)
        except Exception as exc:
            source_error = type(exc).__name__
        try:
            target_data[table] = read_table(target_connection, target_schema, table)
        except Exception as exc:
            target_error = type(exc).__name__
        if source_error or target_error:
            table_reports[table] = {
                "status": "ERROR",
                "source_error": source_error,
                "target_error": target_error,
            }
            continue
        source_columns, source_rows = source_data[table]
        target_columns, target_rows = target_data[table]
        table_reports[table] = compare_table(
            table,
            source_columns,
            source_rows,
            target_columns,
            target_rows,
        )

    checked_tables = set(source_data) | set(target_data)
    source_rows_by_table = {
        table: rows for table, (_, rows) in source_data.items() if table in checked_tables
    }
    target_rows_by_table = {
        table: rows for table, (_, rows) in target_data.items() if table in checked_tables
    }
    statuses = {report["status"] for report in table_reports.values()}
    if "ERROR" in statuses:
        overall_status = "ERROR"
    elif "MISSING" in statuses:
        overall_status = "MISSING"
    elif "MISMATCH" in statuses:
        overall_status = "MISMATCH"
    else:
        overall_status = "MATCH"
    return {
        "status": overall_status,
        "status_legend": list(PARITY_STATUSES),
        "timestamp_policy": TIMESTAMP_POLICY,
        "tables": table_reports,
        "foreign_keys": {
            "source": _foreign_key_report(source_rows_by_table),
            "target": _foreign_key_report(target_rows_by_table),
        },
        "source_summary": _semantic_summary(source_rows_by_table),
        "target_summary": _semantic_summary(target_rows_by_table),
        "not_checked": [table for table in TABLE_NAMES if table not in checked_tables],
    }
