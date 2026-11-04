"""Run one bounded OpenLigaDB synchronization pass."""

from __future__ import annotations

import argparse
from pathlib import Path

from sports_tracker.config import (
    ConfigurationError,
    load_openligadb_settings,
    load_sync_settings,
)
from sports_tracker.openligadb import OpenLigaDBClient, RetryPolicy
from sports_tracker.runtime import open_sql_server_connection
from sports_tracker.synchronization import (
    RunLock,
    SafeJsonLogger,
    SyncAlreadyRunningError,
    SyncCoordinator,
    SyncError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matchday",
        type=int,
        action="append",
        help="Matchday to synchronize; repeat to override configured matchdays.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        source = load_openligadb_settings()
        sync = load_sync_settings()
        matchdays = tuple(args.matchday) if args.matchday else sync.matchdays
        if any(matchday < 1 for matchday in matchdays):
            raise ConfigurationError("Matchdays must be positive integers")
        logger = SafeJsonLogger(sync.log_directory)
        client = OpenLigaDBClient(
            source,
            retry_policy=RetryPolicy(
                max_retries=sync.max_retries,
                initial_backoff_seconds=sync.initial_backoff_seconds,
                max_backoff_seconds=sync.max_backoff_seconds,
            ),
        )
        coordinator = SyncCoordinator(
            client=client,
            connection_factory=open_sql_server_connection,
            raw_directory=Path(source.raw_snapshot_directory),
            shortcut=source.shortcut,
            season=source.season,
            logger=logger,
        )
        with RunLock(sync.lock_file):
            outcomes = coordinator.synchronize(matchdays)
    except SyncAlreadyRunningError as exc:
        print(f"Synchronization not started: {exc}")
        return 3
    except (ConfigurationError, SyncError, OSError) as exc:
        print(f"Synchronization failed safely: {exc}")
        return 1
    except Exception as exc:
        print(f"Synchronization failed safely ({type(exc).__name__}).")
        return 1

    for outcome in outcomes:
        detail = f"matchday {outcome.matchday}: {outcome.status}"
        if outcome.snapshot_sha256:
            detail += f" ({outcome.snapshot_sha256})"
        print(detail)
    print("Synchronization pass completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
