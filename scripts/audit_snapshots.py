"""Inventory preserved raw snapshots; database reconciliation is explicit and read-only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sports_tracker.config import ConfigurationError, load_database_settings
from sports_tracker.database import database_connection
from sports_tracker.snapshot_audit import (
    SnapshotAuditError,
    SnapshotReconciliation,
    inventory_as_dict,
    load_sqlserver_snapshot_references,
    reconcile_snapshot_references,
    scan_snapshot_directory,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("data/raw"),
        help="local raw-snapshot directory; no database or network access is used by default",
    )
    parser.add_argument(
        "--sqlserver",
        action="store_true",
        help="also reconcile dbo.source_snapshots using a read-only SQL Server connection",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="optional report path outside the raw-snapshot directory",
    )
    return parser


def _print_report(report: dict[str, object], reconciliation: SnapshotReconciliation | None) -> None:
    print(f"Snapshot root: {report['root']}")
    print(f"Snapshot pairs: {report['snapshot_pair_count']}")
    print(f"Inventory entries: {report['entry_count']}")
    print("Summary by matchday:")
    for matchday, count in dict(report["matchday_counts"]).items():
        print(f"  {matchday}: {count}")
    duplicate_hashes = report["duplicate_response_hashes"]
    print(f"Duplicate response hashes: {len(duplicate_hashes)}")
    for group in duplicate_hashes:
        print(f"  {group['sha256']}: {len(group['directories'])} retrievals")
    for entry in report["entries"]:
        print(
            f"  {entry['directory']}: matchday={entry['matchday']}; "
            f"status={entry['status']}; "
            f"bytes={entry['actual_byte_count']}/{entry['declared_byte_count']}; "
            f"sha256={entry['actual_sha256']}/{entry['declared_sha256']}"
        )
        if entry["status"] != "valid":
            print("  details: " + "; ".join(entry["errors"]))
    if reconciliation is not None:
        print(f"DB-referenced snapshots: {len(reconciliation.referenced_snapshot_ids)}")
        print(
            "Missing referenced: "
            f"{len(reconciliation.missing_referenced_snapshot_ids)}; "
            "corrupt referenced: "
            f"{len(reconciliation.corrupt_referenced_snapshot_ids)}"
        )
        print(
            f"Unreferenced local directories: {len(reconciliation.unreferenced_local_directories)}"
        )
        print(
            "Interpretation: unreferenced local files are retained evidence, not permission "
            "to delete or deduplicate them."
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = args.root.expanduser().resolve(strict=False)
        inventory = scan_snapshot_directory(root)
        reconciliation = None
        if args.sqlserver:
            with database_connection(load_database_settings()) as connection:
                references = load_sqlserver_snapshot_references(connection)
            reconciliation = reconcile_snapshot_references(inventory, references)
        report = inventory_as_dict(inventory, reconciliation)
        if args.json_output is not None:
            output = args.json_output.expanduser().resolve(strict=False)
            if output.is_relative_to(root):
                raise SnapshotAuditError("JSON report must not be written under data/raw")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (ConfigurationError, OSError, SnapshotAuditError) as exc:
        print(f"Snapshot audit failed safely: {exc}", file=sys.stderr)
        return 2

    _print_report(report, reconciliation)
    if inventory.corrupt_entries or inventory.missing_file_entries:
        return 1
    if reconciliation is not None and reconciliation.has_failure:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
