"""Optional psycopg connection helpers for the PostgreSQL deployment path."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except ModuleNotFoundError:  # pragma: no cover - exercised only in SQL Server-only installs
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    ConnectionPool = None  # type: ignore[assignment]

from .config import PostgreSQLSettings, load_postgresql_settings


def connect_postgresql(settings: PostgreSQLSettings | None = None) -> Any:
    """Open a TLS-configured PostgreSQL transaction connection."""

    if psycopg is None:
        raise RuntimeError("PostgreSQL support requires the psycopg runtime dependency")
    resolved = settings or load_postgresql_settings()
    return psycopg.connect(
        resolved.database_url,
        connect_timeout=max(1, int(resolved.connect_timeout_seconds)),
        options=f"-c statement_timeout={resolved.statement_timeout_ms}",
        sslmode=resolved.sslmode,
        channel_binding=resolved.channel_binding,
        row_factory=dict_row,
        autocommit=False,
    )


@contextmanager
def postgresql_connection(
    settings: PostgreSQLSettings | None = None,
) -> Iterator[Any]:
    """Yield a PostgreSQL connection and close it on every exit path."""

    connection = connect_postgresql(settings)
    try:
        yield connection
    finally:
        connection.close()


PostgreSQLConnectionFactory = Callable[[], Any]


class _PooledConnection:
    """Connection proxy returning a checked-out connection to the pool on close."""

    def __init__(self, pool: Any) -> None:
        self._context = pool.connection()
        self._connection = self._context.__enter__()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def close(self) -> None:
        self._context.__exit__(None, None, None)


class PostgreSQLConnectionPool:
    """Bounded pool for API reads; synchronization uses a direct connection."""

    def __init__(self, settings: PostgreSQLSettings) -> None:
        if ConnectionPool is None:
            raise RuntimeError("PostgreSQL pooling requires the psycopg pool dependency")
        self._pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=settings.pool_min_size,
            max_size=settings.pool_max_size,
            kwargs={
                "connect_timeout": max(1, int(settings.connect_timeout_seconds)),
                "options": f"-c statement_timeout={settings.statement_timeout_ms}",
                "sslmode": settings.sslmode,
                "channel_binding": settings.channel_binding,
                "row_factory": dict_row,
                "autocommit": False,
            },
            open=True,
        )

    def __call__(self) -> Any:
        return _PooledConnection(self._pool)

    def close(self) -> None:
        self._pool.close()
