"""Reusable pyodbc connection helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pyodbc

from .config import DatabaseSettings, build_connection_string, load_database_settings


def connect_database(settings: DatabaseSettings | None = None) -> pyodbc.Connection:
    """Open a SQL Server connection using validated local settings."""

    resolved_settings = settings or load_database_settings()
    return pyodbc.connect(build_connection_string(resolved_settings), autocommit=False)


@contextmanager
def database_connection(
    settings: DatabaseSettings | None = None,
) -> Iterator[pyodbc.Connection]:
    """Yield a connection and always close it when the context exits."""

    connection = connect_database(settings)
    try:
        yield connection
    finally:
        connection.close()
