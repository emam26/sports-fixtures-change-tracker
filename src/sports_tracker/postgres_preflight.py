"""Read-only PostgreSQL deployment preflight checks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REQUIRED_TABLES = (
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
    "schema_migrations",
)


def build_preflight_report(
    database_name: str,
    database_user: str,
    table_presence: Mapping[str, bool],
    *,
    schema: str = "public",
) -> dict[str, Any]:
    missing = [table for table in REQUIRED_TABLES if not table_presence.get(table, False)]
    return {
        "status": "PASS" if not missing else "FAIL",
        "database": database_name,
        "user": database_user,
        "schema": schema,
        "missing_tables": missing,
        "tables": {table: bool(table_presence.get(table, False)) for table in REQUIRED_TABLES},
    }


def run_preflight(connection: Any, *, schema: str = "public") -> dict[str, Any]:
    """Check identity and required tables without writing to PostgreSQL."""

    cursor = connection.cursor()
    try:
        cursor.execute("SELECT current_database(), current_user")
        identity = cursor.fetchone()
        if isinstance(identity, Mapping):
            database_name = str(identity.get("current_database", ""))
            database_user = str(identity.get("current_user", ""))
        else:
            database_name, database_user = (str(value) for value in identity)
        presence: dict[str, bool] = {}
        for table in REQUIRED_TABLES:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                )
                """,
                (schema, table),
            )
            result = cursor.fetchone()
            presence[table] = bool(
                result[0] if not isinstance(result, Mapping) else next(iter(result.values()))
            )
        return build_preflight_report(database_name, database_user, presence, schema=schema)
    finally:
        close = getattr(cursor, "close", None)
        if close is not None:
            close()
