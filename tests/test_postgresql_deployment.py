"""Offline regression coverage for the PostgreSQL and deployment foundations."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts.migrate_sqlserver_to_postgres import (
    MigrationMismatchError,
    _fetch_target_row,
    _fetch_target_rows,
    _validated_schema,
    stable_row_hash,
)

from sports_tracker.api.postgres_repository import PostgreSQLRepository
from sports_tracker.config import ConfigurationError, load_postgresql_settings
from sports_tracker.ingestion import FixtureData, TeamData
from sports_tracker.postgres_ingestion import PostgreSQLImportStore
from sports_tracker.storage import LocalSnapshotStore, SnapshotStorageError


def test_postgresql_settings_redact_dsn_and_require_tls() -> None:
    settings = load_postgresql_settings(
        dotenv_path=Path("missing.env"),
        environ={
            "POSTGRES_DATABASE_URL": "postgresql://tracker:secret@example.test/db",
            "POSTGRES_SSLMODE": "verify-full",
        },
    )

    assert settings.sslmode == "verify-full"
    assert settings.channel_binding == "require"
    assert "secret" not in repr(settings)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("POSTGRES_DATABASE_URL", "https://example.test/db"),
        ("POSTGRES_SSLMODE", "disable"),
    ],
)
def test_postgresql_settings_reject_unsafe_values(key: str, value: str) -> None:
    values = {"POSTGRES_DATABASE_URL": "postgresql://tracker@example.test/db", key: value}
    with pytest.raises(ConfigurationError):
        load_postgresql_settings(dotenv_path=Path("missing.env"), environ=values)


def test_public_postgresql_settings_require_certificate_verification() -> None:
    with pytest.raises(ConfigurationError):
        load_postgresql_settings(
            dotenv_path=Path("missing.env"),
            environ={
                "POSTGRES_DATABASE_URL": "postgresql://tracker@example.test/db",
                "API_DEPLOYMENT_MODE": "public_readonly",
                "POSTGRES_SSLMODE": "require",
            },
        )


def test_stable_row_hash_normalizes_utc_datetimes_and_bytes() -> None:
    value = datetime(2026, 11, 11, 12, tzinfo=UTC)
    assert stable_row_hash(((value, b"snapshot"),)) == stable_row_hash(
        (("2026-11-11T12:00:00+00:00", "736e617073686f74"),)
    )


class _Cursor:
    def __init__(self) -> None:
        self.description = None
        self.rows: list[tuple[object, ...]] = []
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, statement: str, parameters: tuple[object, ...] = ()) -> None:
        self.statements.append((statement, parameters))
        if "COUNT(*) AS total" in statement:
            self.description = (("total",),)
            self.rows = [(2,)]
        else:
            self.description = (
                ("match_id",),
                ("provider_match_id",),
                ("matchday_number",),
                ("stage_name",),
                ("kickoff_utc",),
                ("is_finished",),
                ("home_team",),
                ("away_team",),
                ("home_score",),
                ("away_score",),
                ("last_source_update_utc",),
            )
            self.rows = [
                (1, 87412, 2, "League phase", None, False, "Home", "Away", None, None, None)
            ]

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _Cursor:
        return self._cursor

    def close(self) -> None:
        return None


def test_postgresql_repository_sorts_before_pagination() -> None:
    cursor = _Cursor()
    repository = PostgreSQLRepository(lambda: _Connection(cursor))

    items, total = repository.matches(
        competition_season_id=1,
        matchday=2,
        finished=None,
        search="Bayern",
        limit=10,
        offset=20,
    )

    assert total == 2
    assert items[0]["provider_match_id"] == 87412
    statement, parameters = cursor.statements[-1]
    assert "LEFT JOIN LATERAL" in statement
    assert "ORDER BY" in statement
    assert "OFFSET %s LIMIT %s" in statement
    assert parameters[-2:] == (20, 10)


class _ReturningCursor:
    description = (("new_id",),)

    def __init__(self) -> None:
        self.statement = ""
        self.parameters: tuple[object, ...] = ()

    def execute(self, statement: str, parameters: tuple[object, ...] = ()) -> None:
        self.statement = statement
        self.parameters = parameters

    def fetchone(self) -> tuple[int]:
        return (41,)


class _MappingCursor:
    def execute(self, statement: str, parameters: tuple[object, ...] = ()) -> None:
        del statement, parameters

    def fetchone(self) -> dict[str, object]:
        return {"provider": "OpenLigaDB", "competition_id": 41}

    def fetchall(self) -> list[dict[str, object]]:
        return [{"provider": "OpenLigaDB", "competition_id": 41}]


def test_migration_normalizes_dict_rows_from_psycopg() -> None:
    cursor = _MappingCursor()
    connection = _Connection(cursor)  # type: ignore[arg-type]

    row = _fetch_target_row(
        connection,
        "competitions",
        "competition_id",
        ("competition_id", "provider"),
        41,
        "public",
    )

    assert row == (41, "OpenLigaDB")

    rows = _fetch_target_rows(
        connection,
        "competitions",
        "competition_id",
        ("competition_id", "provider"),
        "public",
    )

    assert rows == [(41, "OpenLigaDB")]


def test_migration_rejects_unsafe_schema_identifier() -> None:
    with pytest.raises(MigrationMismatchError, match="simple SQL identifier"):
        _validated_schema('public".unsafe')


def test_postgresql_repository_rejects_unsafe_schema_identifier() -> None:
    with pytest.raises(ValueError, match="simple SQL identifier"):
        PostgreSQLRepository(lambda: _Connection(_Cursor()), schema='public".unsafe')


def test_postgresql_import_store_uses_fixture_fields_and_returning_id() -> None:
    cursor = _ReturningCursor()
    connection = _Connection(cursor)
    fixture = FixtureData(
        provider_match_id=87412,
        competition_name="UEFA Champions League",
        home_team=TeamData(1, "Home", None, None, None, None, None),
        away_team=TeamData(2, "Away", None, None, None, None, None),
        matchday_number=2,
        source_group_id=None,
        source_group_order_id=None,
        source_group_name=None,
        kickoff_utc=None,
        match_is_finished=False,
        source_last_update_raw=None,
        source_time_zone_id=None,
        location=None,
        results=(),
        goals=(),
    )

    match_id = PostgreSQLImportStore(connection).insert_match(fixture, 1, 11, 12)

    assert match_id == 41
    assert "RETURNING match_id AS new_id" in cursor.statement
    assert "source_last_update_utc" not in cursor.statement
    assert len(cursor.parameters) == 14


def test_local_snapshot_store_rejects_overwrite_and_hash_mismatch(tmp_path: Path) -> None:
    store = LocalSnapshotStore(tmp_path)
    body = b'{"matchData": []}'
    metadata = {"sha256": "bad"}
    with pytest.raises(SnapshotStorageError):
        store.put("ucl/2026/matchday-2/snapshot", body, metadata)
    assert not (tmp_path / "ucl/2026/matchday-2/snapshot").exists()

    metadata["sha256"] = hashlib.sha256(body).hexdigest()
    store.put("ucl/2026/matchday-2/snapshot", body, metadata)
    with pytest.raises(SnapshotStorageError):
        store.put("ucl/2026/matchday-2/snapshot", body, metadata)
