"""Fetch and capture one OpenLigaDB matchday."""

from __future__ import annotations

import argparse
import sys

from sports_tracker.config import ConfigurationError, load_openligadb_settings
from sports_tracker.openligadb import OpenLigaDBClient, OpenLigaDBError
from sports_tracker.snapshots import SnapshotAlreadyExistsError, save_raw_snapshot


def _positive_matchday(value: str) -> int:
    try:
        matchday = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("matchday must be a positive integer") from exc
    if matchday <= 0:
        raise argparse.ArgumentTypeError("matchday must be a positive integer")
    return matchday


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture one OpenLigaDB matchday")
    parser.add_argument(
        "--matchday",
        required=True,
        type=_positive_matchday,
        help="positive OpenLigaDB matchday number",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_openligadb_settings()
        response = OpenLigaDBClient(settings).fetch_matchday(args.matchday)
        snapshot = save_raw_snapshot(response, settings, args.matchday)
    except ConfigurationError as exc:
        print(f"OpenLigaDB fetch failed: {exc}", file=sys.stderr)
        return 1
    except SnapshotAlreadyExistsError:
        print("OpenLigaDB fetch failed: the raw snapshot already exists.", file=sys.stderr)
        return 1
    except OpenLigaDBError as exc:
        print(f"OpenLigaDB fetch failed: {exc}", file=sys.stderr)
        return 1
    except OSError:
        print("OpenLigaDB fetch failed: could not write the raw snapshot.", file=sys.stderr)
        return 1

    print(f"Match count: {len(response.records)}")
    print(f"Snapshot location: {snapshot.directory}")
    print(f"SHA-256: {snapshot.sha256}")
    print("OpenLigaDB matchday snapshot captured successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
