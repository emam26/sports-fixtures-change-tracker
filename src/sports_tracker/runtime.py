"""Runtime adapters that keep secrets out of application output."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    import pyodbc
except ModuleNotFoundError:  # pragma: no cover - exercised in PostgreSQL-only deployments
    pyodbc = None  # type: ignore[assignment]

from sports_tracker.config import (
    load_database_backend,
    load_database_settings,
    load_postgresql_settings,
)
from sports_tracker.postgres import PostgreSQLConnectionPool, connect_postgresql


def _connection_string(settings: object) -> str:
    """Return the validated connection string exposed by Stage 0 configuration."""
    for name in ("connection_string", "build_connection_string", "odbc_connection_string"):
        value = getattr(settings, name, None)
        if value is None:
            continue
        result = value() if callable(value) else value
        if isinstance(result, str) and result:
            return result
    raise RuntimeError("SQL Server settings do not expose a connection string builder")


def open_sql_server_connection() -> Any:
    """Open a transaction-capable SQL Server connection from validated settings."""
    if pyodbc is None:
        raise RuntimeError("SQL Server support requires the sqlserver optional dependency")
    settings = load_database_settings()
    return pyodbc.connect(_connection_string(settings), autocommit=False)


def open_postgresql_connection() -> Any:
    """Open the configured PostgreSQL connection for cloud or local PG use."""

    return connect_postgresql(load_postgresql_settings())


def open_configured_connection() -> Any:
    """Open the explicitly selected database backend."""

    backend = load_database_backend()
    if backend == "postgresql":
        return open_postgresql_connection()
    return open_sql_server_connection()


def configured_repository() -> Any:
    """Build the API repository selected by ``DATABASE_BACKEND``."""

    if load_database_backend() == "postgresql":
        from sports_tracker.api.postgres_repository import PostgreSQLRepository

        settings = load_postgresql_settings()
        pool = PostgreSQLConnectionPool(settings)
        return PostgreSQLRepository(pool, schema=settings.schema)

    from sports_tracker.api.repository import SQLServerRepository

    return SQLServerRepository(open_sql_server_connection)


ConnectionFactory = Callable[[], Any]
