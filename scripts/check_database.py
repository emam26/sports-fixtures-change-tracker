"""Run a read-only SQL Server connection check."""

from __future__ import annotations

import sys

import pyodbc

from sports_tracker.config import ConfigurationError
from sports_tracker.database import database_connection

READ_ONLY_QUERY = """
SELECT
    CAST(SERVERPROPERTY(N'ServerName') AS nvarchar(128)) AS server_name,
    SUSER_SNAME() AS login_name,
    DB_NAME() AS database_name,
    CAST(SERVERPROPERTY(N'Edition') AS nvarchar(128)) AS edition,
    CAST(SERVERPROPERTY(N'ProductVersion') AS nvarchar(128)) AS product_version;
"""


def main() -> int:
    try:
        with database_connection() as connection:
            row = connection.execute(READ_ONLY_QUERY).fetchone()
    except ConfigurationError as exc:
        print(f"Database check failed: {exc}", file=sys.stderr)
        return 1
    except pyodbc.Error:
        print(
            "Database check failed: the read-only SQL Server check could not be completed.",
            file=sys.stderr,
        )
        return 1

    if row is None:
        print("Database check failed: no server metadata row was returned.", file=sys.stderr)
        return 1

    server_name, login_name, database_name, edition, product_version = row
    print("Database connection succeeded.")
    print(f"Server name: {server_name}")
    print(f"Login name: {login_name}")
    print(f"Database name: {database_name}")
    print(f"Edition: {edition}")
    print(f"Product version: {product_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
