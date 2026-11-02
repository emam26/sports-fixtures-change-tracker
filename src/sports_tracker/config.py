"""Environment-backed SQL Server configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


class ConfigurationError(ValueError):
    """Raised when the local database configuration is missing or invalid."""


@dataclass(frozen=True, repr=False)
class DatabaseSettings:
    """Validated settings needed to connect to SQL Server."""

    host: str
    port: int
    database: str
    user: str
    password: str
    encrypt: str
    trust_server_certificate: str

    def __repr__(self) -> str:
        """Return a diagnostic representation that never includes the password."""

        return (
            "DatabaseSettings("
            f"host={self.host!r}, "
            f"port={self.port!r}, "
            f"database={self.database!r}, "
            f"user={self.user!r}, "
            "password='<redacted>', "
            f"encrypt={self.encrypt!r}, "
            f"trust_server_certificate={self.trust_server_certificate!r})"
        )

    @property
    def connection_string(self) -> str:
        """Build the complete connection string for pyodbc use."""

        return build_connection_string(self)


def escape_odbc_value(value: str) -> str:
    """Brace-quote an ODBC value and escape closing braces safely."""

    if not isinstance(value, str):
        raise TypeError("ODBC connection-string values must be strings")
    return "{" + value.replace("}", "}}") + "}"


def _required_value(values: Mapping[str, str], key: str) -> str:
    value = values.get(key)
    if value is None or not str(value).strip():
        raise ConfigurationError(f"Missing required database setting: {key}")
    return str(value)


def _yes_or_no(values: Mapping[str, str], key: str) -> str:
    value = _required_value(values, key).strip().lower()
    if value in {"yes", "true", "1"}:
        return "yes"
    if value in {"no", "false", "0"}:
        return "no"
    raise ConfigurationError(f"Database setting {key} must be yes or no")


def _read_local_values(dotenv_path: str | Path | None) -> dict[str, str]:
    path = Path(dotenv_path) if dotenv_path is not None else Path.cwd() / ".env"
    if not path.is_file():
        return {}
    return {key: value for key, value in dotenv_values(path).items() if value is not None}


def load_database_settings(
    dotenv_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> DatabaseSettings:
    """Load `.env` values, overridden by process environment values, and validate them."""

    values = _read_local_values(dotenv_path)
    values.update(dict(os.environ if environ is None else environ))

    host = _required_value(values, "SQL_SERVER_HOST").strip()
    database = _required_value(values, "SQL_SERVER_DATABASE").strip()
    user = _required_value(values, "SQL_SERVER_USER").strip()
    password = _required_value(values, "SQL_SERVER_PASSWORD")

    port_text = _required_value(values, "SQL_SERVER_PORT").strip()
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ConfigurationError("SQL_SERVER_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ConfigurationError("SQL_SERVER_PORT must be between 1 and 65535")

    return DatabaseSettings(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        encrypt=_yes_or_no(values, "SQL_SERVER_ENCRYPT"),
        trust_server_certificate=_yes_or_no(values, "SQL_SERVER_TRUST_CERTIFICATE"),
    )


def build_connection_string(settings: DatabaseSettings) -> str:
    """Build a SQL Server ODBC Driver 18 connection string."""

    values = [
        ("DRIVER", "ODBC Driver 18 for SQL Server"),
        ("SERVER", f"tcp:{settings.host},{settings.port}"),
        ("DATABASE", settings.database),
        ("UID", settings.user),
        ("PWD", settings.password),
        ("Encrypt", settings.encrypt),
        ("TrustServerCertificate", settings.trust_server_certificate),
    ]
    return ";".join(f"{key}={escape_odbc_value(value)}" for key, value in values) + ";"
