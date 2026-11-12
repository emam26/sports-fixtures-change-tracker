from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts.migrate_snapshots_to_object_storage import SnapshotMigrationError, _read_transfer

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
