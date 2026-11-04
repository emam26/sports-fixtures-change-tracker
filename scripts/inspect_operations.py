"""Print non-secret import and checkpoint diagnostics from SQL Server."""

from __future__ import annotations

import argparse
from contextlib import closing

from sports_tracker.runtime import open_sql_server_connection


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.limit <= 200:
        print("--limit must be between 1 and 200.")
        return 2
    try:
        with closing(open_sql_server_connection()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT TOP (?) import_run_id, status, started_at_utc,
                       completed_at_utc, matches_seen, matches_inserted,
                       matches_updated, validation_issue_count
                FROM dbo.import_runs
                ORDER BY started_at_utc DESC, import_run_id DESC;
                """,
                (args.limit,),
            )
            runs = cursor.fetchall()
            cursor.execute(
                """
                SELECT provider, scope_key, matchday_number,
                       last_source_update_utc, last_processed_at_utc,
                       last_successful_import_run_id
                FROM dbo.sync_checkpoints
                ORDER BY provider, scope_key;
                """
            )
            checkpoints = cursor.fetchall()
    except Exception as exc:
        print(f"Operational inspection failed safely ({type(exc).__name__}).")
        return 1

    print("Recent import runs:")
    for row in runs:
        print(tuple(row))
    print("Synchronization checkpoints:")
    for row in checkpoints:
        print(tuple(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
