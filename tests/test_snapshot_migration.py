from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import pytest
import scripts.migrate_snapshots_to_object_storage as migration
from scripts.migrate_snapshots_to_object_storage import (
    SnapshotMigrationError,
    _read_transfer,
    _row_value,
)

from sports_tracker.config import ObjectStorageSettings


def _object_settings() -> ObjectStorageSettings:
    return ObjectStorageSettings(
        endpoint_url="https://objects.example.test",
        bucket="private-bucket",
        region="us-east-1",
        access_key_id="access-key",
        secret_access_key="secret-key",
    )


def test_snapshot_migration_reconciles_exact_response_and_metadata(tmp_path: Path) -> None:
    body = b'[{"matchID": 87412}]'
    digest = hashlib.sha256(body).hexdigest()
    metadata = {
        "provider": "OpenLigaDB",
        "url": "https://api.openligadb.de/getmatchdata/ucl/2026/2",
        "shortcut": "ucl",
        "season": 2026,
        "matchday": 2,
        "retrieved_at_utc": "2026-11-12T00:00:00Z",
        "http_status": 200,
        "content_type": "application/json",
        "byte_count": len(body),
        "sha256": digest,
    }
    response_path = tmp_path / "response.json"
    metadata_path = tmp_path / "metadata.json"
    response_path.write_bytes(body)
    metadata_path.write_bytes(
        (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )
    row = (
        17,
        "OpenLigaDB",
        "ucl",
        4946,
        2026,
        2,
        metadata["url"],
        "2026-11-12T00:00:00Z",
        200,
        "application/json",
        len(body),
        digest,
        str(tmp_path),
        str(response_path),
        str(metadata_path),
    )

    transfer = _read_transfer(row, _object_settings())

    assert transfer.source_snapshot_id == 17
    assert transfer.body == body
    assert transfer.metadata_bytes == metadata_path.read_bytes()
    assert transfer.sha256 == digest
    assert transfer.object_key.endswith(digest)


def test_snapshot_migration_rejects_corrupt_referenced_file(tmp_path: Path) -> None:
    body = b"actual"
    digest = hashlib.sha256(b"expected").hexdigest()
    metadata = {
        "provider": "OpenLigaDB",
        "url": "https://api.openligadb.de/getmatchdata/ucl/2026/2",
        "shortcut": "ucl",
        "season": 2026,
        "matchday": 2,
        "retrieved_at_utc": "2026-11-12T00:00:00Z",
        "http_status": 200,
        "content_type": "application/json",
        "byte_count": len(b"expected"),
        "sha256": digest,
    }
    response_path = tmp_path / "response.json"
    metadata_path = tmp_path / "metadata.json"
    response_path.write_bytes(body)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    row = (
        17,
        "OpenLigaDB",
        "ucl",
        4946,
        2026,
        2,
        metadata["url"],
        "2026-11-12T00:00:00Z",
        200,
        "application/json",
        len(b"expected"),
        digest,
        str(tmp_path),
        str(response_path),
        str(metadata_path),
    )

    with pytest.raises(SnapshotMigrationError, match="response bytes"):
        _read_transfer(row, _object_settings())


def test_snapshot_migration_reads_psycopg_mapping_rows() -> None:
    row = {"sha256": "digest", "local_directory": "local-key"}

    assert _row_value(row, "sha256", 0) == "digest"
    assert _row_value(row, "local_directory", 1) == "local-key"


class _MigrationCursor:
    def __init__(self, rows: list[tuple[object, ...]], *, update_count: int = 1) -> None:
        self.rows = rows
        self.update_count = update_count
        self.rowcount = -1
        self.statements: list[str] = []

    def execute(self, statement: str, parameters: tuple[object, ...] = ()) -> None:
        del parameters
        self.statements.append(statement)
        if statement.lstrip().upper().startswith("UPDATE"):
            self.rowcount = self.update_count

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


class _MigrationConnection:
    def __init__(self, rows: list[tuple[object, ...]], *, update_count: int = 1) -> None:
        self.cursor_instance = _MigrationCursor(rows, update_count=update_count)
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self) -> _MigrationCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1


class _RecordingStore:
    def __init__(self) -> None:
        self.uploads: list[str] = []

    def put_files(
        self,
        key: str,
        body: bytes,
        metadata_bytes: bytes,
        *,
        expected_sha256: str,
    ) -> None:
        del body, metadata_bytes, expected_sha256
        self.uploads.append(key)


def _transfer(tmp_path: Path) -> migration.SnapshotTransfer:
    body = b'[{"matchID": 87412}]'
    digest = hashlib.sha256(body).hexdigest()
    local_directory = tmp_path / "ucl" / "2026" / "matchday-2" / "capture"
    local_directory.mkdir(parents=True)
    response_path = local_directory / "response.json"
    metadata_path = local_directory / "metadata.json"
    metadata = {
        "provider": "OpenLigaDB",
        "shortcut": "ucl",
        "season": 2026,
        "matchday": 2,
        "url": "https://api.openligadb.de/getmatchdata/ucl/2026/2",
        "retrieved_at_utc": "2026-11-12T00:00:00Z",
        "http_status": 200,
        "content_type": "application/json",
        "byte_count": len(body),
        "sha256": digest,
    }
    response_path.write_bytes(body)
    metadata_bytes = (json.dumps(metadata, indent=2) + "\n").encode()
    metadata_path.write_bytes(metadata_bytes)
    return migration._read_transfer(
        (
            17,
            "OpenLigaDB",
            "ucl",
            4946,
            2026,
            2,
            metadata["url"],
            metadata["retrieved_at_utc"],
            200,
            "application/json",
            len(body),
            digest,
            str(local_directory),
            str(response_path),
            str(metadata_path),
        ),
        _object_settings(),
    )


def _patch_migration_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    transfer: migration.SnapshotTransfer,
    target: _MigrationConnection,
    store: _RecordingStore,
) -> None:
    @contextmanager
    def source_connection(settings: object):
        del settings
        yield object()

    @contextmanager
    def target_connection(settings: object):
        del settings
        yield target

    monkeypatch.setattr(migration, "database_connection", source_connection)
    monkeypatch.setattr(migration, "postgresql_connection", target_connection)
    monkeypatch.setattr(migration, "load_database_settings", lambda: object())
    monkeypatch.setattr(migration, "load_postgresql_settings", lambda: object())
    monkeypatch.setattr(migration, "load_object_storage_settings", lambda: _object_settings())
    monkeypatch.setattr(migration, "_load_transfers", lambda settings: [transfer])
    monkeypatch.setattr(migration, "NeonS3SnapshotStore", lambda settings: store)


def _target_row(transfer: migration.SnapshotTransfer) -> tuple[object, ...]:
    return (
        transfer.source_snapshot_id,
        transfer.sha256,
        len(transfer.body),
        transfer.old_local_directory,
        f"{transfer.old_local_directory}/response.json",
        f"{transfer.old_local_directory}/metadata.json",
    )


def test_snapshot_migration_apply_commits_after_verified_upload(tmp_path, monkeypatch) -> None:
    transfer = _transfer(tmp_path)
    target = _MigrationConnection([_target_row(transfer)])
    store = _RecordingStore()
    _patch_migration_dependencies(monkeypatch, transfer, target, store)

    assert migration.migrate_snapshots(apply=True) == 1
    assert target.commit_count == 1
    assert target.rollback_count == 0
    assert store.uploads == [transfer.object_key]


def test_snapshot_migration_failure_rolls_back_and_reports_uploaded_key(
    tmp_path,
    monkeypatch,
) -> None:
    transfer = _transfer(tmp_path)
    target = _MigrationConnection([_target_row(transfer)], update_count=0)
    store = _RecordingStore()
    _patch_migration_dependencies(monkeypatch, transfer, target, store)

    with pytest.raises(SnapshotMigrationError, match="possible orphan keys"):
        migration.migrate_snapshots(apply=True)

    assert target.commit_count == 0
    assert target.rollback_count == 1
    assert store.uploads == [transfer.object_key]


def test_snapshot_migration_preview_rolls_back_without_upload_or_commit(
    tmp_path,
    monkeypatch,
) -> None:
    transfer = _transfer(tmp_path)
    target = _MigrationConnection([_target_row(transfer)])
    store = _RecordingStore()
    _patch_migration_dependencies(monkeypatch, transfer, target, store)

    assert migration.migrate_snapshots(apply=False) == 1
    assert target.commit_count == 0
    assert target.rollback_count == 1
    assert store.uploads == []


def test_snapshot_migration_rejects_unexpected_target_snapshot(tmp_path, monkeypatch) -> None:
    transfer = _transfer(tmp_path)
    unexpected = (
        99,
        transfer.sha256,
        len(transfer.body),
        "other",
        "other/response.json",
        "other/metadata.json",
    )
    target = _MigrationConnection([_target_row(transfer), unexpected])
    store = _RecordingStore()
    _patch_migration_dependencies(monkeypatch, transfer, target, store)

    with pytest.raises(SnapshotMigrationError, match="unexpected source snapshots"):
        migration.migrate_snapshots(apply=True)

    assert target.commit_count == 0
    assert target.rollback_count == 1
    assert store.uploads == []


def test_snapshot_migration_rejects_target_locator_mismatch(tmp_path, monkeypatch) -> None:
    transfer = _transfer(tmp_path)
    target_row = list(_target_row(transfer))
    target_row[4] = "wrong/response.json"
    target = _MigrationConnection([tuple(target_row)])
    store = _RecordingStore()
    _patch_migration_dependencies(monkeypatch, transfer, target, store)

    with pytest.raises(SnapshotMigrationError, match="inconsistent response"):
        migration.migrate_snapshots(apply=True)

    assert target.commit_count == 0
    assert target.rollback_count == 1
    assert store.uploads == []


def test_snapshot_migration_rejects_target_hash_mismatch(tmp_path, monkeypatch) -> None:
    transfer = _transfer(tmp_path)
    target_row = list(_target_row(transfer))
    target_row[1] = "d" * 64
    target = _MigrationConnection([tuple(target_row)])
    store = _RecordingStore()
    _patch_migration_dependencies(monkeypatch, transfer, target, store)

    with pytest.raises(SnapshotMigrationError, match="hash mismatch"):
        migration.migrate_snapshots(apply=True)

    assert target.commit_count == 0
    assert target.rollback_count == 1
    assert store.uploads == []
