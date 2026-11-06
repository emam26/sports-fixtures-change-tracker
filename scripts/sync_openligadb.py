"""Run one bounded OpenLigaDB synchronization pass."""

from __future__ import annotations

import argparse

from sports_tracker.config import (
    ConfigurationError,
    load_openligadb_settings,
    load_sync_settings,
)
from sports_tracker.openligadb import (
    OpenLigaDBClient,
    OpenLigaDBError,
    RetryPolicy,
    SeasonDiscovery,
)
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
        help="Matchday to synchronize; repeat to bypass source discovery.",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Discover provider-advertised matchdays before synchronizing.",
    )
    parser.add_argument(
        "--include-post-league-phase",
        action="store_true",
        help="Include discovered groups outside configured league-phase matchdays.",
    )
    return parser


def _validate_matchdays(matchdays: tuple[int, ...]) -> tuple[int, ...]:
    if not matchdays or any(matchday < 1 for matchday in matchdays):
        raise ConfigurationError("Matchdays must contain positive integers")
    if len(set(matchdays)) != len(matchdays):
        raise ConfigurationError("Matchdays must not contain duplicates")
    return tuple(sorted(matchdays))


def _select_matchdays(
    args: argparse.Namespace,
    *,
    source,
    sync,
    client: OpenLigaDBClient,
) -> tuple[tuple[int, ...], SeasonDiscovery | None]:
    requested = tuple(args.matchday or ())
    if requested:
        if args.discover or args.include_post_league_phase:
            raise ConfigurationError(
                "--matchday cannot be combined with discovery selection options"
            )
        return _validate_matchdays(requested), None

    if args.discover or sync.discover_matchdays:
        discovery = client.discover_matchdays()
        include_post_league_phase = args.include_post_league_phase or sync.include_post_league_phase
        matchdays = discovery.candidate_matchdays
        if not include_post_league_phase:
            configured_league_phase = set(source.expected_league_phase_matchdays)
            matchdays = tuple(
                matchday for matchday in matchdays if matchday in configured_league_phase
            )
        if not matchdays:
            raise ConfigurationError(
                "Source discovery found no matchdays within the configured synchronization scope"
            )
        return _validate_matchdays(matchdays), discovery

    return _validate_matchdays(sync.matchdays), None


def main() -> int:
    args = build_parser().parse_args()
    try:
        source = load_openligadb_settings()
        sync = load_sync_settings()
        logger = SafeJsonLogger(sync.log_directory)
        client = OpenLigaDBClient(
            source,
            retry_policy=RetryPolicy(
                max_retries=sync.max_retries,
                initial_backoff_seconds=sync.backoff_initial_seconds,
                max_backoff_seconds=sync.backoff_max_seconds,
            ),
        )
        matchdays, discovery = _select_matchdays(
            args,
            source=source,
            sync=sync,
            client=client,
        )
        if discovery is not None:
            logger.write(
                "sync_matchdays_discovered",
                matchdays=matchdays,
                available_group_matchdays=discovery.available_group_matchdays,
                full_season_matchdays=discovery.full_season_matchdays,
                warning_count=len(discovery.warnings),
            )
        coordinator = SyncCoordinator(
            client=client,
            connection_factory=open_sql_server_connection,
            logger=logger,
        )
        with RunLock(sync.lock_file):
            logger.write("sync_run_started", matchdays=matchdays)
            outcomes = coordinator.synchronize(matchdays)
    except SyncAlreadyRunningError as exc:
        print(f"Synchronization not started: {exc}")
        return 3
    except (ConfigurationError, OpenLigaDBError, SyncError, OSError) as exc:
        print(f"Synchronization failed safely: {exc}")
        return 1
    except Exception as exc:
        print(f"Synchronization failed safely ({type(exc).__name__}).")
        return 1

    for outcome in outcomes:
        detail = f"matchday {outcome.matchday}: {outcome.status}"
        if outcome.snapshot_sha256:
            detail += f" ({outcome.snapshot_sha256})"
        if outcome.snapshot_directory:
            detail += f" snapshot={outcome.snapshot_directory}"
        print(detail)
    failed = sum(outcome.status == "failed" for outcome in outcomes)
    try:
        logger.write(
            "sync_run_completed",
            matchday_count=len(outcomes),
            failed_matchdays=failed,
        )
    except OSError:
        print("Synchronization outcomes were produced, but the completion log failed.")
        return 1
    if failed:
        print(f"Synchronization pass completed with {failed} failed matchday(s).")
        return 1
    print("Synchronization pass completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
