"""Measure deterministic offline snapshot parsing without importing data."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from time import perf_counter

from sports_tracker.config import (
    ConfigurationError,
    load_object_storage_settings,
    load_openligadb_settings,
)
from sports_tracker.ingestion import SnapshotValidationError, load_snapshot
from sports_tracker.storage import NeonS3SnapshotStore, SnapshotStorageError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, nargs="?")
    parser.add_argument(
        "--object-key",
        help="read one immutable snapshot from configured private object storage",
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


def main() -> int:
    args = build_parser().parse_args()
    if (args.snapshot is None) == (args.object_key is None):
        print("Offline evaluation requires exactly one local snapshot or --object-key")
        return 2
    try:
        settings = load_openligadb_settings()
        started = perf_counter()
        display_snapshot = args.object_key or args.snapshot.resolve()
        if args.object_key is not None:
            blob = NeonS3SnapshotStore(load_object_storage_settings()).get(args.object_key)
            body = blob.body
            settings.raw_snapshot_directory.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                dir=settings.raw_snapshot_directory,
                prefix="object-replay-",
            ) as temporary_directory:
                snapshot = Path(temporary_directory)
                snapshot.joinpath("response.json").write_bytes(blob.body)
                snapshot.joinpath("metadata.json").write_bytes(
                    blob.metadata_bytes
                    or (json.dumps(blob.metadata, indent=2, ensure_ascii=False) + "\n").encode(
                        "utf-8"
                    )
                )
                parsed = load_snapshot(
                    snapshot,
                    settings,
                    allow_conflicting_nonfinal_results=args.allow_conflicting_nonfinal_results,
                )
                elapsed_ms = (perf_counter() - started) * 1000
        else:
            snapshot = args.snapshot.resolve()
            body = (snapshot / "response.json").read_bytes()
            parsed = load_snapshot(
                snapshot,
                settings,
                allow_conflicting_nonfinal_results=args.allow_conflicting_nonfinal_results,
            )
            elapsed_ms = (perf_counter() - started) * 1000
    except (ConfigurationError, OSError, SnapshotValidationError, SnapshotStorageError) as exc:
        print(f"Offline evaluation failed safely: {exc}")
        return 1
    print(f"Snapshot: {display_snapshot}")
    print(f"SHA-256: {hashlib.sha256(body).hexdigest()}")
    print(f"Matches parsed: {len(parsed.matches)}")
    print(f"Parse latency: {elapsed_ms:.3f} ms")
    print("No database writes or network requests were performed by this command.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
