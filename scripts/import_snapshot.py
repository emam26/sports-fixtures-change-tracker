"""Validate and import one preserved OpenLigaDB snapshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyodbc

from sports_tracker.config import (
    ConfigurationError,
    load_database_settings,
    load_openligadb_settings,
)
from sports_tracker.database import database_connection
from sports_tracker.ingestion import (
    ImportExecutionError,
    SnapshotImportProcessor,
    SnapshotValidationError,
    SQLServerImportStore,
    ValidationIssue,
    load_snapshot,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate or import one preserved OpenLigaDB snapshot"
    )
    parser.add_argument(
        "--snapshot",
        required=True,
        type=Path,
        help="snapshot directory, response.json, or metadata.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and summarize the snapshot without opening SQL Server",
    )
    parser.add_argument(
        "--allow-conflicting-nonfinal-results",
        action="store_true",
        help=(
            "quarantine conflicting HalfTime variants for this manual snapshot only; "
            "never selects a provider variant"
        ),
    )
    return parser


def _print_issues(issues: tuple[ValidationIssue, ...]) -> None:
    for issue in issues:
        print(
            f"{issue.severity}: {issue.code}: {issue.message}"
            + (f" [match {issue.source_record_id}]" if issue.source_record_id else ""),
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source_settings = load_openligadb_settings()
        if args.allow_conflicting_nonfinal_results:
            parsed = load_snapshot(
                args.snapshot,
                source_settings,
                allow_conflicting_nonfinal_results=True,
            )
        else:
            parsed = load_snapshot(args.snapshot, source_settings)
    except (ConfigurationError, SnapshotValidationError, OSError) as exc:
        print(f"Snapshot import failed: {exc}", file=sys.stderr)
        return 2

    if parsed.issues:
        _print_issues(parsed.issues)
    if args.dry_run:
        if parsed.errors:
            print(
                f"Dry run failed: {len(parsed.errors)} error(s) in "
                f"{len(parsed.matches)} valid match record(s).",
                file=sys.stderr,
            )
            return 2
        print(f"Dry run validation passed: {len(parsed.matches)} match(es).")
        print(f"Result records: {sum(len(match.results) for match in parsed.matches)}")
        print(f"Goal records: {sum(len(match.goals) for match in parsed.matches)}")
        print(f"Snapshot SHA-256: {parsed.metadata.sha256}")
        return 0

    try:
        database_settings = load_database_settings()
        with database_connection(database_settings) as connection:
            summary = SnapshotImportProcessor(
                SQLServerImportStore(connection, parsed.metadata.provider)
            ).import_snapshot(parsed)
    except ConfigurationError as exc:
        print(f"Snapshot import failed: {exc}", file=sys.stderr)
        return 2
    except ImportExecutionError as exc:
        print(
            f"Snapshot import failed: {exc}. "
            "Inspect the reported rollback outcome and failed import run manually.",
            file=sys.stderr,
        )
        return 3
    except (OSError, pyodbc.Error):
        print(
            "Snapshot import failed: could not access the configured database.",
            file=sys.stderr,
        )
        return 3

    print(f"Import status: {summary.status}")
    print(f"Import run ID: {summary.import_run_id}")
    print(f"Source snapshot ID: {summary.source_snapshot_id}")
    print(f"Matches: {summary.matches_seen}")
    print(f"Inserted: {summary.matches_inserted}")
    print(f"Updated: {summary.matches_updated}")
    print(f"Unchanged: {summary.matches_unchanged}")
    print(f"Results observed: {summary.results_seen}")
    print(f"Goals observed: {summary.goals_seen}")
    print(f"Changes recorded: {summary.changes_recorded}")
    print(f"Validation issues: {summary.validation_issue_count}")
    if summary.status != "Succeeded":
        return 4
    print("Snapshot import completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
