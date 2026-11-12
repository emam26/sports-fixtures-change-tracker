"""PostgreSQL checkpoint and lease adapters for unattended synchronization."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime
from uuid import uuid4

from .runtime import ConnectionFactory
from .synchronization import MatchdaySyncState, SyncAlreadyRunningError, _utc_datetime


def _row_value(row, key: str, index: int):
    return row[key] if isinstance(row, dict) else row[index]


class PostgreSQLCheckpointReader:
    """Read source checkpoints using PostgreSQL parameter markers and syntax."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def last_source_update(
        self,
        *,
        provider: str,
        shortcut: str,
        season: int,
        matchday: int,
    ) -> datetime | None:
        with closing(self._connection_factory()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT sc.last_source_update_utc
                FROM sync_checkpoints AS sc
                INNER JOIN competition_seasons AS cs
                    ON cs.competition_season_id = sc.competition_season_id
                INNER JOIN competitions AS c ON c.competition_id = cs.competition_id
                WHERE sc.provider = %s
                  AND c.provider_shortcut = %s
                  AND cs.season_start_year = %s
                  AND sc.matchday_number = %s
                """,
                (provider, shortcut, season, matchday),
            )
            row = cursor.fetchone()
        return None if row is None else _utc_datetime(_row_value(row, "last_source_update_utc", 0))


class PostgreSQLMatchdayReader:
    """Read matchday state used by conservative sync selection."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def states(
        self,
        *,
        provider: str,
        shortcut: str,
        season: int,
    ) -> tuple[MatchdaySyncState, ...]:
        with closing(self._connection_factory()) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT m.matchday_number, COUNT(*) AS match_count,
                       SUM(CASE WHEN NOT m.source_match_is_finished THEN 1 ELSE 0 END)
                           AS unfinished_count,
                       MIN(CASE WHEN NOT m.source_match_is_finished THEN m.kickoff_utc END)
                           AS nearest_unfinished_kickoff_utc,
                       MAX(CASE WHEN m.source_match_is_finished THEN m.kickoff_utc END)
                           AS latest_finished_kickoff_utc,
                       MAX(sc.last_processed_at_utc) AS last_processed_at_utc
                FROM matches AS m
                INNER JOIN competition_seasons AS cs
                    ON cs.competition_season_id = m.competition_season_id
                INNER JOIN competitions AS c ON c.competition_id = cs.competition_id
                LEFT JOIN sync_checkpoints AS sc
                    ON sc.competition_season_id = m.competition_season_id
                   AND sc.matchday_number = m.matchday_number
                   AND sc.provider = c.provider
                WHERE c.provider = %s
                  AND c.provider_shortcut = %s
                  AND cs.season_start_year = %s
                  AND m.matchday_number IS NOT NULL
                GROUP BY m.matchday_number
                ORDER BY m.matchday_number
                """,
                (provider, shortcut, season),
            )
            rows = cursor.fetchall()
        return tuple(
            MatchdaySyncState(
                matchday=int(_row_value(row, "matchday_number", 0)),
                match_count=int(_row_value(row, "match_count", 1) or 0),
                unfinished_count=int(_row_value(row, "unfinished_count", 2) or 0),
                nearest_unfinished_kickoff_utc=_utc_datetime(
                    _row_value(row, "nearest_unfinished_kickoff_utc", 3)
                ),
                latest_finished_kickoff_utc=_utc_datetime(
                    _row_value(row, "latest_finished_kickoff_utc", 4)
                ),
                last_processed_at_utc=_utc_datetime(_row_value(row, "last_processed_at_utc", 5)),
            )
            for row in rows
        )


class PostgreSQLSyncLease:
    """Database-backed lease that covers manual and scheduled PostgreSQL syncs."""

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        lease_key: str = "OpenLigaDB:sync",
        lease_seconds: int = 1_800,
    ) -> None:
        self._connection_factory = connection_factory
        self._lease_key = lease_key
        self._lease_seconds = lease_seconds
        self._owner_token = uuid4().hex
        self._connection = None

    def acquire(self) -> None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "DELETE FROM sync_leases "
                "WHERE lease_key = %s AND expires_at_utc <= CURRENT_TIMESTAMP",
                (self._lease_key,),
            )
            cursor.execute(
                """
                INSERT INTO sync_leases (lease_key, owner_token, expires_at_utc)
                VALUES (%s, %s, CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'))
                """,
                (self._lease_key, self._owner_token, self._lease_seconds),
            )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            connection.close()
            if getattr(exc, "sqlstate", None) != "23505":
                raise
            raise SyncAlreadyRunningError(
                "a PostgreSQL synchronization lease is already held"
            ) from exc
        self._connection = connection
        self._start_heartbeat()

    def _start_heartbeat(self) -> None:
        import threading

        stop_event = threading.Event()
        self._heartbeat_stop = stop_event

        def keep_alive() -> None:
            interval = max(1.0, min(self._lease_seconds / 3, 60.0))
            while not stop_event.wait(interval):
                try:
                    self.renew()
                except Exception:
                    self._heartbeat_error = True
                    stop_event.set()
                    return

        heartbeat = threading.Thread(
            target=keep_alive,
            name="sports-tracker-sync-lease",
            daemon=True,
        )
        self._heartbeat_thread = heartbeat
        heartbeat.start()

    def renew(self) -> None:
        """Extend the lease only while this owner still holds it."""

        connection = self._connection
        if connection is None:
            raise RuntimeError("cannot renew a PostgreSQL sync lease that is not held")

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE sync_leases
                    SET expires_at_utc = CURRENT_TIMESTAMP
                        + (%s * INTERVAL '1 second')
                    WHERE lease_key = %s
                      AND owner_token = %s
                      AND expires_at_utc > CURRENT_TIMESTAMP
                    """,
                    (self._lease_seconds, self._lease_key, self._owner_token),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    self.release()
                    raise SyncAlreadyRunningError(
                        "the PostgreSQL synchronization lease was lost before renewal"
                    )
            connection.commit()
        except SyncAlreadyRunningError:
            raise
        except Exception:
            connection.rollback()
            raise

    def release(self) -> None:
        import threading

        stop_event = getattr(self, "_heartbeat_stop", None)
        if stop_event is not None:
            stop_event.set()
        heartbeat = getattr(self, "_heartbeat_thread", None)
        if heartbeat is not None and heartbeat is not threading.current_thread():
            heartbeat.join(timeout=2)
        if self._connection is None:
            return
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                "DELETE FROM sync_leases WHERE lease_key = %s AND owner_token = %s",
                (self._lease_key, self._owner_token),
            )
            self._connection.commit()
        finally:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> PostgreSQLSyncLease:
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()
