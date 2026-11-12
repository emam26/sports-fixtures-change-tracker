import pytest

from sports_tracker.postgres_synchronization import (
    PostgreSQLSyncLease,
    SyncAlreadyRunningError,
)


class _Cursor:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount
        self.executed = []

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, parameters: tuple[object, ...]) -> None:
        self.executed.append((statement, parameters))


class _Connection:
    def __init__(self, rowcount: int) -> None:
        self.cursor_instance = _Cursor(rowcount)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> _Cursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def _lease(connection: _Connection) -> PostgreSQLSyncLease:
    lease = object.__new__(PostgreSQLSyncLease)
    lease._connection = connection
    lease._lease_seconds = 1800
    lease._lease_key = "test"
    lease._owner_token = "owner"
    return lease


def test_lease_renewal_commits_only_when_owner_row_is_updated() -> None:
    connection = _Connection(rowcount=1)
    lease = _lease(connection)

    lease.renew()

    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.cursor_instance.executed


def test_lease_renewal_fails_closed_when_owner_lost() -> None:
    connection = _Connection(rowcount=0)
    lease = _lease(connection)

    with pytest.raises(SyncAlreadyRunningError):
        lease.renew()

    assert connection.rollbacks == 1
    assert connection.closed
