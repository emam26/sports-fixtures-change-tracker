"""Environment-backed SQL Server configuration."""

from __future__ import annotations

import math
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
    expected_league_phase_matchdays: tuple[int, ...] = tuple(range(1, 9))
    expected_fixtures_per_matchday: int = 18


@dataclass(frozen=True)
class SyncSettings:
    """Validated one-shot synchronization settings."""

    matchdays: tuple[int, ...]
    max_retries: int
    backoff_initial_seconds: float
    backoff_max_seconds: float
    lock_file: Path
    log_directory: Path
    discover_matchdays: bool = True
    include_post_league_phase: bool = False


@dataclass(frozen=True, repr=False)
class ApplicationSettings:
    """Validated local API security settings."""

    local_only: bool
    allow_note_writes: bool
    notes_write_token: str | None

    def __repr__(self) -> str:
        return (
            "ApplicationSettings("
            f"local_only={self.local_only!r}, "
            f"allow_note_writes={self.allow_note_writes!r}, "
            "notes_write_token='<redacted>')"
        )


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


def _boolean_value(
    values: Mapping[str, str],
    key: str,
    *,
    default: bool,
) -> bool:
    raw_value = values.get(key)
    if raw_value is None or not str(raw_value).strip():
        return default
    value = str(raw_value).strip().lower()
    if value in {"yes", "true", "1"}:
        return True
    if value in {"no", "false", "0"}:
        return False
    raise ConfigurationError(f"Setting {key} must be yes or no")


def _optional_positive_float(
    values: Mapping[str, str],
    key: str,
    *,
    default: float,
) -> float:
    raw_value = values.get(key)
    if raw_value is None or not str(raw_value).strip():
        return default
    try:
        value = float(str(raw_value).strip())
    except ValueError as exc:
        raise ConfigurationError(f"Setting {key} must be a number") from exc
    if not math.isfinite(value) or value <= 0:
        raise ConfigurationError(f"Setting {key} must be greater than zero")
    return value


def _optional_nonnegative_int(
    values: Mapping[str, str],
    key: str,
    *,
    default: int,
) -> int:
    raw_value = values.get(key)
    if raw_value is None or not str(raw_value).strip():
        return default
    try:
        value = int(str(raw_value).strip())
    except ValueError as exc:
        raise ConfigurationError(f"Setting {key} must be an integer") from exc
    if value < 0:
        raise ConfigurationError(f"Setting {key} must not be negative")
    return value


def _optional_positive_int(
    values: Mapping[str, str],
    key: str,
    *,
    default: int,
) -> int:
    raw_value = values.get(key)
    if raw_value is None or not str(raw_value).strip():
        return default
    try:
        value = int(str(raw_value).strip())
    except ValueError as exc:
        raise ConfigurationError(f"Setting {key} must be an integer") from exc
    if value <= 0:
        raise ConfigurationError(f"Setting {key} must be greater than zero")
    return value


def _positive_int_list(
    values: Mapping[str, str],
    key: str,
    *,
    default: tuple[int, ...],
    allow_empty: bool,
) -> tuple[int, ...]:
    """Read a comma-separated, duplicate-free sequence of positive matchdays."""

    raw_value = values.get(key)
    if raw_value is None:
        return default
    text = str(raw_value).strip()
    if not text:
        if allow_empty:
            return ()
        raise ConfigurationError(f"Setting {key} must contain at least one positive integer")
    try:
        parsed = tuple(int(item.strip()) for item in text.split(","))
    except ValueError as exc:
        raise ConfigurationError(
            f"Setting {key} must be a comma-separated list of integers"
        ) from exc
    if any(matchday <= 0 for matchday in parsed):
        raise ConfigurationError(f"Setting {key} must contain only positive integers")
    if len(set(parsed)) != len(parsed):
        raise ConfigurationError(f"Setting {key} must not contain duplicates")
    return tuple(sorted(parsed))


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
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ConfigurationError("OPENLIGADB_TIMEOUT_SECONDS must be greater than zero")

    raw_directory = _required_value(values, "RAW_SNAPSHOT_DIRECTORY").strip()
    expected_league_phase_matchdays = _positive_int_list(
        values,
        "OPENLIGADB_LEAGUE_PHASE_MATCHDAYS",
        default=tuple(range(1, 9)),
        allow_empty=False,
    )
    expected_fixtures_per_matchday = _optional_positive_int(
        values,
        "OPENLIGADB_EXPECTED_FIXTURES_PER_MATCHDAY",
        default=18,
    )
    return OpenLigaDBSettings(
        base_url=base_url,
        shortcut=shortcut,
        season=season,
        expected_league_id=expected_league_id,
        timeout_seconds=timeout_seconds,
        raw_snapshot_directory=Path(raw_directory),
        expected_league_phase_matchdays=expected_league_phase_matchdays,
        expected_fixtures_per_matchday=expected_fixtures_per_matchday,
    )


def load_sync_settings(
    dotenv_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> SyncSettings:
    """Load conservative synchronization, retry, lock, and log settings."""

    values = _merged_values(dotenv_path, environ)
    matchdays = _positive_int_list(
        values,
        "OPENLIGADB_MATCHDAYS",
        default=(),
        allow_empty=True,
    )

    max_retries = _optional_nonnegative_int(
        values,
        "OPENLIGADB_MAX_RETRIES",
        default=3,
    )
    if max_retries > 10:
        raise ConfigurationError("OPENLIGADB_MAX_RETRIES must not exceed 10")
    backoff_initial = _optional_positive_float(
        values,
        "OPENLIGADB_BACKOFF_INITIAL_SECONDS",
        default=1.0,
    )
    backoff_max = _optional_positive_float(
        values,
        "OPENLIGADB_BACKOFF_MAX_SECONDS",
        default=8.0,
    )
    if backoff_max < backoff_initial:
        raise ConfigurationError(
            "OPENLIGADB_BACKOFF_MAX_SECONDS must be at least the initial backoff"
        )

    lock_file = str(values.get("SYNC_LOCK_FILE", "data/runtime/sync.lock")).strip()
    log_directory = str(values.get("SYNC_LOG_DIRECTORY", "data/runtime/logs")).strip()
    if not lock_file or not log_directory:
        raise ConfigurationError("Synchronization lock and log paths must not be blank")
    return SyncSettings(
        matchdays=matchdays,
        max_retries=max_retries,
        backoff_initial_seconds=backoff_initial,
        backoff_max_seconds=backoff_max,
        lock_file=Path(lock_file),
        log_directory=Path(log_directory),
        discover_matchdays=_boolean_value(
            values,
            "OPENLIGADB_DISCOVER_MATCHDAYS",
            default=True,
        ),
        include_post_league_phase=_boolean_value(
            values,
            "OPENLIGADB_INCLUDE_POST_LEAGUE_PHASE",
            default=False,
        ),
    )


def load_application_settings(
    dotenv_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> ApplicationSettings:
    """Load local-only API and note-write authorization settings."""

    values = _merged_values(dotenv_path, environ)
    local_only = _boolean_value(values, "API_LOCAL_ONLY", default=True)
    allow_note_writes = _boolean_value(
        values,
        "API_ALLOW_NOTE_WRITES",
        default=False,
    )
    token_value = values.get("API_NOTES_WRITE_TOKEN")
    token = None if token_value is None else str(token_value).strip() or None
    if allow_note_writes and (token is None or len(token) < 16):
        raise ConfigurationError(
            "API_NOTES_WRITE_TOKEN must contain at least 16 characters when writes are enabled"
        )
    return ApplicationSettings(
        local_only=local_only,
        allow_note_writes=allow_note_writes,
        notes_write_token=token,
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
