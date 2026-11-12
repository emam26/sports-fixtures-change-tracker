from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from scripts.evaluate_snapshot import build_parser as build_evaluation_parser

from sports_tracker.config import ConfigurationError, load_object_storage_settings
from sports_tracker.storage import (
    NeonS3SnapshotStore,
    SnapshotStorageError,
    build_snapshot_object_key,
)


class _Body:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def read(self) -> bytes:
        return self.value


class _ClientError(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}
        super().__init__(code)


class _FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_metadata_upload = False
        self.fail_delete = False

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, _Body]:
        del Bucket
        if Key not in self.objects:
            raise _ClientError("404")
        return {"Body": _Body(self.objects[Key])}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, IfNoneMatch: str, **kwargs) -> None:
        del Bucket, IfNoneMatch, kwargs
        if self.fail_metadata_upload and Key.endswith("metadata.json"):
            raise RuntimeError("synthetic metadata upload failure")
        if Key in self.objects:
            raise _ClientError("PreconditionFailed")
        self.objects[Key] = Body

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        del Bucket
        if self.fail_delete:
            raise RuntimeError("synthetic cleanup failure")
        self.objects.pop(Key, None)


def _settings():
    from sports_tracker.config import ObjectStorageSettings

    return ObjectStorageSettings(
        endpoint_url="https://objects.example.test",
        bucket="private-bucket",
        region="us-east-1",
        access_key_id="access-key",
        secret_access_key="secret-key",
    )


def _metadata(body: bytes) -> dict[str, object]:
    return {
        "provider": "OpenLigaDB",
        "shortcut": "ucl",
        "season": 2026,
        "matchday": 3,
        "retrieved_at_utc": "2026-11-12T00:00:00Z",
        "byte_count": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def test_object_key_is_deterministic_and_content_addressed() -> None:
    settings = _settings()
    key = build_snapshot_object_key(
        settings,
        shortcut="ucl",
        season=2026,
        matchday=3,
        retrieved_at_utc="2026-11-12T00:00:00Z",
        sha256="a" * 64,
    )

    assert key.endswith("/ucl/2026/matchday-3/20261112T000000000000Z_" + "a" * 64)
    assert (
        build_snapshot_object_key(
            settings,
            shortcut="ucl",
            season=2026,
            matchday=3,
            retrieved_at_utc="2026-11-12T00:00:00Z",
            sha256="a" * 64,
        )
        == key
    )


def test_object_store_upload_download_and_idempotent_retry() -> None:
    client = _FakeS3()
    store = NeonS3SnapshotStore(_settings(), client=client)
    body = b'[{"matchID": 1}]'
    metadata = _metadata(body)
    key = "sports-fixtures/raw/ucl/2026/matchday-3/snapshot"

    store.put(key, body, metadata)
    store.put(key, body, metadata)

    loaded = store.get(key)
    assert loaded.body == body
    assert loaded.metadata == json.loads(
        (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )


def test_object_store_rejects_mismatch_and_corruption() -> None:
    client = _FakeS3()
    store = NeonS3SnapshotStore(_settings(), client=client)
    body = b"original"
    metadata = _metadata(body)
    key = "snapshot"
    store.put(key, body, metadata)

    with pytest.raises(SnapshotStorageError, match="immutable object content mismatch"):
        store.put(key, b"different", _metadata(b"different"))

    client.objects["snapshot/response.json"] = b"corrupt"
    with pytest.raises(SnapshotStorageError, match="hash verification failed"):
        store.get(key)


def test_object_store_cleans_new_response_after_metadata_upload_failure() -> None:
    client = _FakeS3()
    client.fail_metadata_upload = True
    store = NeonS3SnapshotStore(_settings(), client=client)

    with pytest.raises(SnapshotStorageError, match="could not store object"):
        store.put("snapshot", b"body", _metadata(b"body"))

    assert client.objects == {}

    client.fail_metadata_upload = False
    store.put("snapshot", b"body", _metadata(b"body"))
    assert client.objects["snapshot/response.json"] == b"body"


def test_object_store_repairs_a_matching_partial_pair_without_overwriting_response() -> None:
    client = _FakeS3()
    body = b"body"
    client.objects["snapshot/response.json"] = body
    store = NeonS3SnapshotStore(_settings(), client=client)

    store.put("snapshot", body, _metadata(body))

    assert client.objects["snapshot/response.json"] == body
    assert client.objects["snapshot/metadata.json"]


def test_object_store_reports_orphan_when_cleanup_cannot_complete() -> None:
    client = _FakeS3()
    client.fail_metadata_upload = True
    client.fail_delete = True
    store = NeonS3SnapshotStore(_settings(), client=client)

    with pytest.raises(SnapshotStorageError, match="possible orphan objects"):
        store.put("snapshot", b"body", _metadata(b"body"))

    assert client.objects["snapshot/response.json"] == b"body"


def test_object_store_rejects_conflicting_partial_pair_without_deleting_existing_object() -> None:
    client = _FakeS3()
    body = b"body"
    client.objects["snapshot/response.json"] = body
    client.objects["snapshot/metadata.json"] = b"conflicting"
    store = NeonS3SnapshotStore(_settings(), client=client)

    with pytest.raises(SnapshotStorageError, match="immutable object content mismatch"):
        store.put("snapshot", body, _metadata(body))

    assert client.objects["snapshot/response.json"] == body
    assert client.objects["snapshot/metadata.json"] == b"conflicting"


def test_object_storage_loader_requires_all_credentials_and_redacts_them() -> None:
    values = {
        "OBJECT_STORAGE_ENDPOINT_URL": "https://objects.example.test",
        "OBJECT_STORAGE_BUCKET": "private-bucket",
        "OBJECT_STORAGE_REGION": "us-east-1",
        "OBJECT_STORAGE_ACCESS_KEY_ID": "access-key",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": "secret-key",
    }
    settings = load_object_storage_settings(environ=values)

    assert "secret-key" not in repr(settings)
    assert settings.endpoint_url == "https://objects.example.test"

    with pytest.raises(ConfigurationError, match="must use HTTPS"):
        load_object_storage_settings(
            environ={
                **values,
                "OBJECT_STORAGE_ENDPOINT_URL": "http://objects.example.test",
            },
        )

    with pytest.raises(ConfigurationError, match="OBJECT_STORAGE_SECRET_ACCESS_KEY"):
        incomplete = {
            key: value for key, value in values.items() if key != "OBJECT_STORAGE_SECRET_ACCESS_KEY"
        }
        load_object_storage_settings(environ=incomplete)


def test_synchronization_workflow_is_explicitly_gated() -> None:
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "synchronize.yml").read_text(
        encoding="utf-8"
    )

    assert "inputs.activate" in workflow
    assert "vars.ENABLE_SYNC == 'true'" in workflow
    assert "RAW_SNAPSHOT_STORAGE: object" in workflow


def test_postgresql_role_script_has_no_password_literals_or_domain_delete_grant() -> None:
    role_sql = (Path(__file__).parents[1] / "sql" / "postgresql" / "002_roles.sql").read_text(
        encoding="utf-8"
    )

    executable_sql = re.sub(r"--[^\r\n]*|/\*.*?\*/", "", role_sql, flags=re.MULTILINE | re.DOTALL)
    assert "PASSWORD" not in executable_sql.upper()
    delete_grants = re.findall(
        r"GRANT\s+([^;]+?)\s+ON\s+TABLE\s+([^;]+?)\s+TO\s+[^;]+;",
        executable_sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert all(
        "DELETE" not in privileges.upper()
        or tables.strip().upper() in {"SYNC_LEASES", "PUBLIC.SYNC_LEASES"}
        for privileges, tables in delete_grants
    )
    assert "sports_tracker_api" in role_sql
    assert "sports_tracker_sync" in role_sql
    assert "sports_tracker_migrator" in role_sql


def test_postgresql_role_script_uses_scoped_grants() -> None:
    role_sql = (Path(__file__).parents[1] / "sql" / "postgresql" / "002_roles.sql").read_text(
        encoding="utf-8"
    )

    assert "GRANT SELECT ON ALL TABLES" not in role_sql.upper()
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA public\n    GRANT" not in role_sql
    assert (
        "GRANT SELECT, INSERT, DELETE ON TABLE public.sync_leases TO sports_tracker_sync;"
        in role_sql
    )
    assert "schema_migrations" not in role_sql


def test_evaluation_cli_accepts_a_private_object_key() -> None:
    args = build_evaluation_parser().parse_args(["--object-key", "snapshot/key"])

    assert args.snapshot is None
    assert args.object_key == "snapshot/key"
