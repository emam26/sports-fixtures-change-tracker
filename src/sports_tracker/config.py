"""Environment-backed SQL Server configuration."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

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


@dataclass(frozen=True)
class OpenLigaDBSettings:
    """Validated settings for retrieving OpenLigaDB matchday data."""

    base_url: str
    shortcut: str
    season: int
    expected_league_id: int
    timeout_seconds: float
    raw_snapshot_directory: Path
    user_agent: str = "sports-fixtures-change-tracker/0.1 (OpenLigaDB client)"


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


def _merged_values(
    dotenv_path: str | Path | None,
    environ: Mapping[str, str] | None,
) -> dict[str, str]:
    values = _read_local_values(dotenv_path)
    values.update(dict(os.environ if environ is None else environ))
    return values


def load_database_settings(
    dotenv_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> DatabaseSettings:
    """Load `.env` values, overridden by process environment values, and validate them."""

    values = _merged_values(dotenv_path, environ)

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


def _validated_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ConfigurationError(
            "OPENLIGADB_BASE_URL must be an HTTP(S) URL without credentials or query parameters"
        )
    return base_url


def _positive_int(values: Mapping[str, str], key: str) -> int:
    value = _required_value(values, key).strip()
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"Database/source setting {key} must be an integer") from exc
    if parsed <= 0:
        raise ConfigurationError(f"Database/source setting {key} must be greater than zero")
    return parsed


def load_openligadb_settings(
    dotenv_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> OpenLigaDBSettings:
    """Load and validate OpenLigaDB source settings from `.env` and the environment."""

    values = _merged_values(dotenv_path, environ)
    base_url = _validated_base_url(_required_value(values, "OPENLIGADB_BASE_URL"))
    shortcut = _required_value(values, "OPENLIGADB_SHORTCUT").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]+", shortcut) is None:
        raise ConfigurationError("OPENLIGADB_SHORTCUT contains unsupported URL path characters")

    season = _positive_int(values, "OPENLIGADB_SEASON")
    expected_league_id = _positive_int(values, "OPENLIGADB_EXPECTED_LEAGUE_ID")
    timeout_text = _required_value(values, "OPENLIGADB_TIMEOUT_SECONDS").strip()
    try:
        timeout_seconds = float(timeout_text)
    except ValueError as exc:
        raise ConfigurationError("OPENLIGADB_TIMEOUT_SECONDS must be a number") from exc
    if timeout_seconds <= 0:
        raise ConfigurationError("OPENLIGADB_TIMEOUT_SECONDS must be greater than zero")

    raw_directory = _required_value(values, "RAW_SNAPSHOT_DIRECTORY").strip()
    return OpenLigaDBSettings(
        base_url=base_url,
        shortcut=shortcut,
        season=season,
        expected_league_id=expected_league_id,
        timeout_seconds=timeout_seconds,
        raw_snapshot_directory=Path(raw_directory),
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
