"""Environment-backed database, source, synchronization, and API configuration."""

from __future__ import annotations

import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from dotenv import dotenv_values


class ConfigurationError(ValueError):
    """Raised when the local database configuration is missing or invalid."""


ApplicationDeploymentMode = Literal["local", "public_readonly"]
DatabaseBackend = Literal["sqlserver", "postgresql"]
SnapshotStorageMode = Literal["local", "object"]


@dataclass(frozen=True, repr=False)
class ObjectStorageSettings:
    """Validated private S3-compatible object-storage settings."""

    endpoint_url: str
    bucket: str
    region: str
    access_key_id: str
    secret_access_key: str
    prefix: str = "sports-fixtures/raw"
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 30.0

    def __repr__(self) -> str:
        return (
            "ObjectStorageSettings(endpoint_url=<redacted>, "
            f"bucket={self.bucket!r}, region={self.region!r}, "
            "access_key_id='<redacted>', secret_access_key='<redacted>', "
            f"prefix={self.prefix!r}, connect_timeout_seconds={self.connect_timeout_seconds!r}, "
            f"read_timeout_seconds={self.read_timeout_seconds!r})"
        )


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


@dataclass(frozen=True, repr=False)
class PostgreSQLSettings:
    """Validated PostgreSQL connection settings for local or cloud runtime use."""

    database_url: str
    sslmode: str
    channel_binding: str
    connect_timeout_seconds: float
    statement_timeout_ms: int
    pool_min_size: int
    pool_max_size: int
    schema: str = "public"

    def __repr__(self) -> str:
        """Return a diagnostic representation that never includes the DSN."""

        return (
            "PostgreSQLSettings(database_url='<redacted>', "
            f"sslmode={self.sslmode!r}, "
            f"channel_binding={self.channel_binding!r}, "
            f"connect_timeout_seconds={self.connect_timeout_seconds!r}, "
            f"statement_timeout_ms={self.statement_timeout_ms!r}, "
            f"pool_min_size={self.pool_min_size!r}, "
            f"pool_max_size={self.pool_max_size!r}, "
            f"schema={self.schema!r})"
        )


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
    raw_snapshot_storage: SnapshotStorageMode = "local"


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
    near_kickoff_window_minutes: int = 180
    near_kickoff_recheck_minutes: int = 30
    recent_completed_window_hours: int = 48
    recent_completed_recheck_hours: int = 6
    older_matchday_interval_hours: int = 168
    max_matchdays_per_run: int = 3


@dataclass(frozen=True, repr=False)
class ApplicationSettings:
    """Validated API deployment and note-write security settings."""

    local_only: bool
    allow_note_writes: bool
    notes_write_token: str | None
    deployment_mode: ApplicationDeploymentMode = "local"

    def __post_init__(self) -> None:
        if self.deployment_mode not in {"local", "public_readonly"}:
            raise ConfigurationError("API_DEPLOYMENT_MODE must be local or public_readonly")
        if self.deployment_mode == "local" and not self.local_only:
            raise ConfigurationError("local mode requires API_LOCAL_ONLY=yes")
        if self.deployment_mode == "public_readonly" and (
            self.local_only or self.allow_note_writes or self.notes_write_token is not None
        ):
            raise ConfigurationError(
                "public_readonly mode requires API_LOCAL_ONLY=no and note writes disabled"
            )
        if self.allow_note_writes and (
            self.notes_write_token is None or len(self.notes_write_token) < 16
        ):
            raise ConfigurationError(
                "API_NOTES_WRITE_TOKEN must contain at least 16 characters when writes are enabled"
            )

    def __repr__(self) -> str:
        return (
            "ApplicationSettings("
            f"local_only={self.local_only!r}, "
            f"allow_note_writes={self.allow_note_writes!r}, "
            f"deployment_mode={self.deployment_mode!r}, "
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


def load_database_backend(
    dotenv_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> DatabaseBackend:
    """Load the explicitly selected persistence backend."""

    values = _merged_values(dotenv_path, environ)
    backend = str(values.get("DATABASE_BACKEND", "sqlserver")).strip().lower()
    if backend not in {"sqlserver", "postgresql"}:
        raise ConfigurationError("DATABASE_BACKEND must be sqlserver or postgresql")
    return backend  # type: ignore[return-value]


def _validated_postgresql_url(value: str) -> str:
    database_url = value.strip()
    parsed = urlsplit(database_url)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or not parsed.netloc
        or not parsed.path.strip("/")
        or parsed.fragment
    ):
        raise ConfigurationError(
            "POSTGRES_DATABASE_URL must be a PostgreSQL URL with a database name"
        )
    return database_url


def load_postgresql_settings(
    dotenv_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> PostgreSQLSettings:
    """Load PostgreSQL settings without exposing the credential-bearing DSN."""

    values = _merged_values(dotenv_path, environ)
    raw_url = values.get("POSTGRES_DATABASE_URL") or values.get("DATABASE_URL")
    if raw_url is None or not str(raw_url).strip():
        raise ConfigurationError(
            "Missing required PostgreSQL setting: POSTGRES_DATABASE_URL or DATABASE_URL"
        )
    database_url = _validated_postgresql_url(str(raw_url))

    sslmode = str(values.get("POSTGRES_SSLMODE", "verify-full")).strip().lower()
    if sslmode not in {"verify-full", "verify-ca", "require"}:
        raise ConfigurationError("POSTGRES_SSLMODE must be verify-full, verify-ca, or require")
    deployment_mode = str(values.get("API_DEPLOYMENT_MODE", "local")).strip().lower()
    if deployment_mode == "public_readonly" and sslmode != "verify-full":
        raise ConfigurationError(
            "public_readonly PostgreSQL deployments require POSTGRES_SSLMODE=verify-full"
        )
    channel_binding = str(values.get("POSTGRES_CHANNEL_BINDING", "require")).strip().lower()
    if channel_binding not in {"require", "prefer", "disable"}:
        raise ConfigurationError("POSTGRES_CHANNEL_BINDING must be require, prefer, or disable")
    schema = str(values.get("POSTGRES_SCHEMA", "public")).strip()
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema) is None:
        raise ConfigurationError("POSTGRES_SCHEMA must be a simple SQL identifier")
    pool_min_size = _optional_nonnegative_int(
        values,
        "POSTGRES_POOL_MIN_SIZE",
        default=0,
    )
    pool_max_size = _optional_positive_int(
        values,
        "POSTGRES_POOL_MAX_SIZE",
        default=2,
    )
    if pool_max_size < pool_min_size:
        raise ConfigurationError("POSTGRES_POOL_MAX_SIZE must be at least the minimum pool size")
    return PostgreSQLSettings(
        database_url=database_url,
        sslmode=sslmode,
        channel_binding=channel_binding,
        connect_timeout_seconds=_optional_positive_float(
            values,
            "POSTGRES_CONNECT_TIMEOUT_SECONDS",
            default=10.0,
        ),
        statement_timeout_ms=_optional_positive_int(
            values,
            "POSTGRES_STATEMENT_TIMEOUT_MS",
            default=30_000,
        ),
        pool_min_size=pool_min_size,
        pool_max_size=pool_max_size,
        schema=schema,
    )


def load_object_storage_settings(
    dotenv_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> ObjectStorageSettings:
    """Load private S3-compatible storage settings without exposing credentials."""

    values = _merged_values(dotenv_path, environ)
    endpoint = _required_value(values, "OBJECT_STORAGE_ENDPOINT_URL").strip().rstrip("/")
    parsed_endpoint = urlsplit(endpoint)
    if (
        parsed_endpoint.scheme not in {"http", "https"}
        or not parsed_endpoint.netloc
        or parsed_endpoint.username is not None
        or parsed_endpoint.password is not None
        or parsed_endpoint.query
        or parsed_endpoint.fragment
    ):
        raise ConfigurationError(
            "OBJECT_STORAGE_ENDPOINT_URL must be an HTTP(S) URL without credentials "
            "or query parameters"
        )
    if parsed_endpoint.scheme != "https":
        raise ConfigurationError("OBJECT_STORAGE_ENDPOINT_URL must use HTTPS")

    bucket = _required_value(values, "OBJECT_STORAGE_BUCKET").strip()
    if "/" in bucket or "\\" in bucket or bucket == "." or bucket == "..":
        raise ConfigurationError("OBJECT_STORAGE_BUCKET must be a single bucket name")
    region = _required_value(values, "OBJECT_STORAGE_REGION").strip()
    access_key_id = _required_value(values, "OBJECT_STORAGE_ACCESS_KEY_ID").strip()
    secret_access_key = _required_value(values, "OBJECT_STORAGE_SECRET_ACCESS_KEY")
    prefix = str(values.get("OBJECT_STORAGE_PREFIX", "sports-fixtures/raw")).strip().strip("/")
    if not prefix or ".." in prefix or "\\" in prefix:
        raise ConfigurationError("OBJECT_STORAGE_PREFIX must be a safe object-key prefix")
    return ObjectStorageSettings(
        endpoint_url=endpoint,
        bucket=bucket,
        region=region,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        prefix=prefix,
        connect_timeout_seconds=_optional_positive_float(
            values,
            "OBJECT_STORAGE_CONNECT_TIMEOUT_SECONDS",
            default=10.0,
        ),
        read_timeout_seconds=_optional_positive_float(
            values,
            "OBJECT_STORAGE_READ_TIMEOUT_SECONDS",
            default=30.0,
        ),
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
    raw_snapshot_storage = str(values.get("RAW_SNAPSHOT_STORAGE", "local")).strip().lower()
    if raw_snapshot_storage not in {"local", "object"}:
        raise ConfigurationError("RAW_SNAPSHOT_STORAGE must be local or object")
    return OpenLigaDBSettings(
        base_url=base_url,
        shortcut=shortcut,
        season=season,
        expected_league_id=expected_league_id,
        timeout_seconds=timeout_seconds,
        raw_snapshot_directory=Path(raw_directory),
        expected_league_phase_matchdays=expected_league_phase_matchdays,
        expected_fixtures_per_matchday=expected_fixtures_per_matchday,
        raw_snapshot_storage=raw_snapshot_storage,  # type: ignore[arg-type]
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
    near_kickoff_window_minutes = _optional_positive_int(
        values,
        "OPENLIGADB_NEAR_KICKOFF_WINDOW_MINUTES",
        default=180,
    )
    near_kickoff_recheck_minutes = _optional_positive_int(
        values,
        "OPENLIGADB_NEAR_KICKOFF_RECHECK_MINUTES",
        default=30,
    )
    recent_completed_window_hours = _optional_positive_int(
        values,
        "OPENLIGADB_RECENT_COMPLETED_WINDOW_HOURS",
        default=48,
    )
    recent_completed_recheck_hours = _optional_positive_int(
        values,
        "OPENLIGADB_RECENT_COMPLETED_RECHECK_HOURS",
        default=6,
    )
    older_matchday_interval_hours = _optional_positive_int(
        values,
        "OPENLIGADB_OLDER_MATCHDAY_INTERVAL_HOURS",
        default=168,
    )
    max_matchdays_per_run = _optional_positive_int(
        values,
        "OPENLIGADB_MAX_MATCHDAYS_PER_RUN",
        default=3,
    )
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
        near_kickoff_window_minutes=near_kickoff_window_minutes,
        near_kickoff_recheck_minutes=near_kickoff_recheck_minutes,
        recent_completed_window_hours=recent_completed_window_hours,
        recent_completed_recheck_hours=recent_completed_recheck_hours,
        older_matchday_interval_hours=older_matchday_interval_hours,
        max_matchdays_per_run=max_matchdays_per_run,
    )


def load_application_settings(
    dotenv_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> ApplicationSettings:
    """Load and validate API deployment and note-write authorization settings."""

    values = _merged_values(dotenv_path, environ)
    deployment_mode = str(values.get("API_DEPLOYMENT_MODE", "local")).strip().lower()
    if deployment_mode not in {"local", "public_readonly"}:
        raise ConfigurationError("API_DEPLOYMENT_MODE must be local or public_readonly")
    local_only = _boolean_value(values, "API_LOCAL_ONLY", default=True)
    allow_note_writes = _boolean_value(
        values,
        "API_ALLOW_NOTE_WRITES",
        default=False,
    )
    if deployment_mode == "local" and not local_only:
        raise ConfigurationError("API_LOCAL_ONLY=no requires API_DEPLOYMENT_MODE=public_readonly")
    if deployment_mode == "public_readonly" and local_only:
        raise ConfigurationError("public_readonly mode requires API_LOCAL_ONLY=no")
    if deployment_mode == "public_readonly" and allow_note_writes:
        raise ConfigurationError("public_readonly mode requires API_ALLOW_NOTE_WRITES=no")
    token_value = values.get("API_NOTES_WRITE_TOKEN")
    token = None if token_value is None else str(token_value).strip() or None
    if deployment_mode == "public_readonly" and token is not None:
        raise ConfigurationError("public_readonly mode requires API_NOTES_WRITE_TOKEN to be blank")
    if allow_note_writes and (token is None or len(token) < 16):
        raise ConfigurationError(
            "API_NOTES_WRITE_TOKEN must contain at least 16 characters when writes are enabled"
        )
    return ApplicationSettings(
        local_only=local_only,
        allow_note_writes=allow_note_writes,
        notes_write_token=token,
        deployment_mode=deployment_mode,
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
