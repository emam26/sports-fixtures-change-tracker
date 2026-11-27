"""Exact-byte archive checks with a disposable PostgreSQL integration target."""

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from sports_tracker.postgres_snapshot_store import (
    ARCHIVE_DATABASE_LIMIT_BYTES,
    PostgreSQLSnapshotStore,
    archive_key,
    check_archive_budget,
    validate_snapshot_bytes,
)
from sports_tracker.storage import SnapshotStorageError

ROOT = Path(__file__).resolve().parents[1]


def _capture():
    body = b'[{"matchID": 123}]\n'
    metadata = {
        "provider": "OpenLigaDB",
        "shortcut": "ucl",
        "season": 2026,
        "matchday": 1,
        "retrieved_at_utc": "2026-11-27T02:17:00Z",
        "sha256": hashlib.sha256(body).hexdigest(),
        "byte_count": len(body),
    }
    return archive_key(metadata), body, (json.dumps(metadata, indent=4) + "\r\n").encode()


def test_exact_bytes_and_archive_identity():
    key, body, metadata = _capture()
    assert validate_snapshot_bytes(key, body, metadata)["matchday"] == 1
    for bad_key, bad_body in ((key + "x", body), (key, body + b"x")):
        with pytest.raises(SnapshotStorageError, match="mismatch"):
            validate_snapshot_bytes(bad_key, bad_body, metadata)


def test_database_size_guard():
    result = SimpleNamespace(fetchone=lambda: {"database_bytes": ARCHIVE_DATABASE_LIMIT_BYTES - 5})
    connection = SimpleNamespace(execute=lambda _: result)
    assert check_archive_budget(connection, 5) == ARCHIVE_DATABASE_LIMIT_BYTES - 5
    with pytest.raises(SnapshotStorageError, match="size guard"):
        check_archive_budget(connection, 6)


@pytest.mark.postgres_archive
def test_postgres_archive_roundtrip_and_role_permissions():
    if os.getenv("RUN_POSTGRES_ARCHIVE_TESTS") != "yes":
        pytest.skip("requires a disposable PostgreSQL archive test database")
    import psycopg
    from psycopg.rows import dict_row

    url = os.environ["POSTGRES_ARCHIVE_TEST_URL"]
    if url == os.getenv("POSTGRES_DATABASE_URL"):
        pytest.fail("archive integration target must not be the configured database")
    key, body, metadata = _capture()
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as connection:
        assert connection.info.dbname == "archive_test"
        for name in ("001_initial_schema.sql", "002_roles.sql", "003_raw_snapshot_archive.sql"):
            connection.execute((ROOT / "sql/postgresql" / name).read_text())
        connection.execute((ROOT / "sql/postgresql/002_roles.sql").read_text())
        connection.execute("CREATE ROLE archive_test_sync LOGIN")
        connection.execute("GRANT sports_tracker_sync TO archive_test_sync")
        connection.execute("SET ROLE archive_test_sync")
        api_access = connection.execute(
            "SELECT has_table_privilege('sports_tracker_api', "
            "'public.raw_snapshot_blobs', 'SELECT') AS allowed"
        ).fetchone()
        assert api_access["allowed"] is False
        connection.autocommit = False
        store = PostgreSQLSnapshotStore(connection)
        store.put_files(key, body, metadata)
        assert store.get(key).metadata_bytes == metadata
        connection.rollback()
        with pytest.raises(SnapshotStorageError, match="missing"):
            store.get(key)
        store.put_files(key, body, metadata)
        connection.commit()
        store.put_files(key, body, metadata)
        assert store.get(key).body == body
        with pytest.raises(SnapshotStorageError, match="immutable"):
            store.put_files(key, body, metadata + b" ")
        connection.commit()
        for statement in (
            "UPDATE public.raw_snapshot_blobs SET metadata_bytes = metadata_bytes",
            "DELETE FROM public.raw_snapshot_blobs",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(statement)
            connection.rollback()
