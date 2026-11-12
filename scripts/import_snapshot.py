"""Validate and import one preserved OpenLigaDB snapshot."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

try:
    import pyodbc
except ModuleNotFoundError:  # pragma: no cover - SQL Server extra is optional in cloud
    pyodbc = None  # type: ignore[assignment]

from sports_tracker.config import (
    ConfigurationError,
    load_database_backend,
    load_database_settings,
    load_object_storage_settings,
    load_openligadb_settings,
    load_postgresql_settings,
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
from sports_tracker.postgres import postgresql_connection
from sports_tracker.postgres_ingestion import PostgreSQLImportStore
from sports_tracker.storage import (
    NeonS3SnapshotStore,
    SnapshotStorageError,
    build_snapshot_object_key,
)

_DATABASE_ERRORS = (OSError, RuntimeError) + ((pyodbc.Error,) if pyodbc is not None else ())


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


def _prepare_postgresql_snapshot(parsed, source_settings):
    if source_settings.raw_snapshot_storage != "object":
        return parsed
    object_settings = load_object_storage_settings()
    body = (parsed.directory / "response.json").read_bytes()
    metadata_bytes = (parsed.directory / "metadata.json").read_bytes()
    key = build_snapshot_object_key(
        object_settings,
        shortcut=parsed.metadata.shortcut,
        season=parsed.metadata.season,
        matchday=parsed.metadata.matchday,
        retrieved_at_utc=parsed.metadata.retrieved_at_utc,
        sha256=parsed.metadata.sha256,
    )
    NeonS3SnapshotStore(object_settings).put_files(
        key,
        body,
        metadata_bytes,
        expected_sha256=parsed.metadata.sha256,
    )
    return replace(parsed, directory=Path(key))


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
        if load_database_backend() == "postgresql":
            database_settings = load_postgresql_settings()
            parsed = _prepare_postgresql_snapshot(parsed, source_settings)
            with postgresql_connection(database_settings) as connection:
                store = PostgreSQLImportStore(connection, parsed.metadata.provider)
                summary = SnapshotImportProcessor(store).import_snapshot(parsed)
        else:
            database_settings = load_database_settings()
            with database_connection(database_settings) as connection:
                store = SQLServerImportStore(connection, parsed.metadata.provider)
                summary = SnapshotImportProcessor(store).import_snapshot(parsed)
    except ConfigurationError as exc:
        print(f"Snapshot import failed: {exc}", file=sys.stderr)
        return 2
    except SnapshotStorageError as exc:
        print(f"Snapshot import failed: durable snapshot storage: {exc}", file=sys.stderr)
        return 3
    except ImportExecutionError as exc:
        print(
            f"Snapshot import failed: {exc}. "
            "Inspect the reported rollback outcome and failed import run manually.",
            file=sys.stderr,
        )
        return 3
    except _DATABASE_ERRORS:
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
