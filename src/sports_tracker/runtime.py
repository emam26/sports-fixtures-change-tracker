"""Runtime adapters that keep secrets out of application output."""

from __future__ import annotations

from collections.abc import Callable

import pyodbc

from sports_tracker.config import load_database_settings


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


def open_sql_server_connection() -> pyodbc.Connection:
    """Open a transaction-capable SQL Server connection from validated settings."""
    settings = load_database_settings()
    return pyodbc.connect(_connection_string(settings), autocommit=False)


ConnectionFactory = Callable[[], pyodbc.Connection]
