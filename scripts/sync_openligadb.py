"""Run one bounded OpenLigaDB synchronization pass."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from sports_tracker.config import (
    ConfigurationError,
    load_database_backend,
    load_object_storage_settings,
    load_openligadb_settings,
    load_sync_settings,
)
from sports_tracker.openligadb import (
    OpenLigaDBClient,
    OpenLigaDBError,
    RetryPolicy,
    SeasonDiscovery,
)
from sports_tracker.postgres_ingestion import PostgreSQLImportStore
from sports_tracker.postgres_synchronization import (
    PostgreSQLCheckpointReader,
    PostgreSQLMatchdayReader,
    PostgreSQLSyncLease,
)
from sports_tracker.runtime import open_postgresql_connection, open_sql_server_connection
from sports_tracker.synchronization import (
    MatchdaySelection,
    MatchdaySyncState,
    RunLock,
    SafeJsonLogger,
    SyncAlreadyRunningError,
    SyncCoordinator,
    SyncError,
    SyncMatchdayReader,
    select_matchdays,
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
    connection_factory,
    matchday_reader_factory=None,
) -> tuple[tuple[int, ...], SeasonDiscovery | None, tuple[MatchdaySelection, ...]]:
    requested = tuple(args.matchday or ())
    if requested:
        if args.discover or args.include_post_league_phase:
            raise ConfigurationError(
                "--matchday cannot be combined with discovery selection options"
            )
        matchdays = _validate_matchdays(requested)
        return (
            matchdays,
            None,
            tuple(MatchdaySelection(matchday, "explicit-cli-request", 0) for matchday in matchdays),
        )

    if sync.matchdays and not args.discover:
        matchdays = _validate_matchdays(sync.matchdays)
        return (
            matchdays,
            None,
            tuple(
                MatchdaySelection(matchday, "explicit-configured-matchday", 0)
                for matchday in matchdays
            ),
        )

    reader = (matchday_reader_factory or SyncMatchdayReader)(connection_factory)
    states = list(
        reader.states(
            provider="OpenLigaDB",
            shortcut=source.shortcut,
            season=source.season,
        )
    )
    discovery: SeasonDiscovery | None = None
    should_discover = args.discover or (sync.discover_matchdays and not states)
    if should_discover:
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
        known = {state.matchday for state in states}
        states.extend(
            MatchdaySyncState(
                matchday=matchday,
                match_count=0,
                unfinished_count=0,
                nearest_unfinished_kickoff_utc=None,
                latest_finished_kickoff_utc=None,
                last_processed_at_utc=None,
            )
            for matchday in matchdays
            if matchday not in known
        )

    if not states:
        raise ConfigurationError(
            "No stored matchdays are available; use --discover or configure OPENLIGADB_MATCHDAYS"
        )

    allowed_matchdays = set(source.expected_league_phase_matchdays)
    if args.include_post_league_phase or sync.include_post_league_phase:
        scoped_states = tuple(states)
    else:
        scoped_states = tuple(state for state in states if state.matchday in allowed_matchdays)
    selections = select_matchdays(
        scoped_states,
        now_utc=datetime.now(UTC),
        near_kickoff_window_minutes=sync.near_kickoff_window_minutes,
        near_kickoff_recheck_minutes=sync.near_kickoff_recheck_minutes,
        recent_completed_window_hours=sync.recent_completed_window_hours,
        recent_completed_recheck_hours=sync.recent_completed_recheck_hours,
        older_matchday_interval_hours=sync.older_matchday_interval_hours,
        max_matchdays=sync.max_matchdays_per_run,
    )
    return tuple(selection.matchday for selection in selections), discovery, selections


def main() -> int:
    args = build_parser().parse_args()
    try:
        source = load_openligadb_settings()
        sync = load_sync_settings()
        if source.raw_snapshot_storage == "object":
            load_object_storage_settings()
        backend = load_database_backend()
        if backend == "postgresql":
            connection_factory = open_postgresql_connection
            matchday_reader = PostgreSQLMatchdayReader
            checkpoint_reader = PostgreSQLCheckpointReader
            store_factory = PostgreSQLImportStore
            sync_lock = PostgreSQLSyncLease(connection_factory)
        else:
            connection_factory = open_sql_server_connection
            matchday_reader = SyncMatchdayReader
            checkpoint_reader = None
            store_factory = None
            sync_lock = RunLock(sync.lock_file)
        logger = SafeJsonLogger(sync.log_directory)
        client = OpenLigaDBClient(
            source,
            retry_policy=RetryPolicy(
                max_retries=sync.max_retries,
                initial_backoff_seconds=sync.backoff_initial_seconds,
                max_backoff_seconds=sync.backoff_max_seconds,
            ),
        )
        with sync_lock:
            matchdays, discovery, selections = _select_matchdays(
                args,
                source=source,
                sync=sync,
                client=client,
                connection_factory=connection_factory,
                matchday_reader_factory=matchday_reader,
            )
            if discovery is not None:
                logger.write(
                    "sync_matchdays_discovered",
                    matchdays=matchdays,
                    available_group_matchdays=discovery.available_group_matchdays,
                    full_season_matchdays=discovery.full_season_matchdays,
                    warning_count=len(discovery.warnings),
                )
            logger.write(
                "sync_matchdays_selected",
                matchdays=matchdays,
                selection_reasons=[
                    {"matchday": selection.matchday, "reason": selection.reason}
                    for selection in selections
                ],
            )
            coordinator = SyncCoordinator(
                client=client,
                connection_factory=connection_factory,
                logger=logger,
                checkpoint_reader_factory=checkpoint_reader,
                store_factory=store_factory,
            )
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
    if not outcomes:
        print("No due matchdays selected; synchronization pass completed.")
        return 0
    print("Synchronization pass completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
