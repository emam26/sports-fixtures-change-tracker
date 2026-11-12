from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import pytest

from sports_tracker.config import load_object_storage_settings, load_postgresql_settings
from sports_tracker.postgres import postgresql_connection
from sports_tracker.storage import NeonS3SnapshotStore


@pytest.fixture(autouse=True)
def _require_dedicated_neon_target(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.getenv("RUN_NEON_INTEGRATION") != "yes":
        return
    if os.getenv("POSTGRES_TEST_CONFIRM_ISOLATED") != "yes":
        pytest.skip("set POSTGRES_TEST_CONFIRM_ISOLATED=yes for a dedicated target")
    test_url = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("set POSTGRES_TEST_DATABASE_URL to a dedicated test database")
    if test_url == os.getenv("POSTGRES_DATABASE_URL"):
        pytest.fail("POSTGRES_TEST_DATABASE_URL must not equal the production URL")
    monkeypatch.setenv("POSTGRES_DATABASE_URL", test_url)


@pytest.mark.neon
def test_opt_in_neon_database_and_object_storage_round_trip() -> None:
    if os.environ.get("RUN_NEON_INTEGRATION") != "yes":
        pytest.skip("set RUN_NEON_INTEGRATION=yes for an isolated Neon verification")

    with postgresql_connection(load_postgresql_settings()) as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1

    body = b'{"verification": true}'
    key = f"verification/{uuid4().hex}"
    store = NeonS3SnapshotStore(load_object_storage_settings())
    metadata = {
        "provider": "verification",
        "shortcut": "test",
        "season": 0,
        "matchday": 1,
        "retrieved_at_utc": "2026-11-12T00:00:00Z",
        "byte_count": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    try:
        store.put(key, body, metadata)
        assert store.get(key).body == body
    finally:
        store.client.delete_object(Bucket=store.bucket, Key=f"{key}/response.json")
        store.client.delete_object(Bucket=store.bucket, Key=f"{key}/metadata.json")
