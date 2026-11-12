"""Reusable optional SQL Server connection helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

try:
    import pyodbc
except ModuleNotFoundError:  # pragma: no cover - exercised in PostgreSQL-only deployments
    pyodbc = None  # type: ignore[assignment]

from .config import DatabaseSettings, build_connection_string, load_database_settings


def connect_database(settings: DatabaseSettings | None = None) -> Any:
    """Open a SQL Server connection using validated local settings."""

    if pyodbc is None:
        raise RuntimeError("SQL Server support requires the sqlserver optional dependency")
    resolved_settings = settings or load_database_settings()
    return pyodbc.connect(build_connection_string(resolved_settings), autocommit=False)


@contextmanager
def database_connection(
    settings: DatabaseSettings | None = None,
) -> Iterator[Any]:
    """Yield a connection and always close it when the context exits."""

    connection = connect_database(settings)
    try:
        yield connection
    finally:
        connection.close()
