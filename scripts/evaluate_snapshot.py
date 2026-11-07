"""Measure deterministic offline snapshot parsing without importing data."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from time import perf_counter

from sports_tracker.config import ConfigurationError, load_openligadb_settings
from sports_tracker.ingestion import SnapshotValidationError, load_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
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
    snapshot = args.snapshot.resolve()
    response_file = snapshot / "response.json"
    try:
        settings = load_openligadb_settings()
        body = response_file.read_bytes()
        started = perf_counter()
        if args.allow_conflicting_nonfinal_results:
            parsed = load_snapshot(
                snapshot,
                settings,
                allow_conflicting_nonfinal_results=True,
            )
        else:
            parsed = load_snapshot(snapshot, settings)
        elapsed_ms = (perf_counter() - started) * 1000
    except (ConfigurationError, OSError, SnapshotValidationError) as exc:
        print(f"Offline evaluation failed safely: {exc}")
        return 1
    print(f"Snapshot: {snapshot}")
    print(f"SHA-256: {hashlib.sha256(body).hexdigest()}")
    print(f"Matches parsed: {len(parsed.matches)}")
    print(f"Parse latency: {elapsed_ms:.3f} ms")
    print("No database writes or network requests were performed by this command.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
