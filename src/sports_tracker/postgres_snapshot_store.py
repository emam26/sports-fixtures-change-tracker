"""Private, immutable exact-byte snapshot archive inside PostgreSQL."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from .storage import SnapshotBlob, SnapshotStorageError, build_snapshot_object_key

# Conservative application guard, not a representation of the provider's quota.
ARCHIVE_DATABASE_LIMIT_BYTES = 400 * 1024 * 1024


@dataclass(frozen=True)
class PostgreSQLArchiveNamespace:
    prefix: str = "postgresql/sports-fixtures/raw"


POSTGRES_ARCHIVE_KEYS = PostgreSQLArchiveNamespace()


def archive_key(metadata: dict[str, Any]) -> str:
    """Use the original retrieval identity, never the time of migration."""
    try:
        shortcut = metadata["shortcut"]
        season = metadata["season"]
        day = metadata["matchday"]
        if (
            metadata["provider"] != "OpenLigaDB"
            or not isinstance(shortcut, str)
            or re.fullmatch(r"[A-Za-z0-9_-]+", shortcut) is None
            or type(season) is not int
            or not 1900 <= season <= 2200
            or type(day) is not int
            or day < 1
        ):
            raise ValueError("invalid source identity")
        return build_snapshot_object_key(
            POSTGRES_ARCHIVE_KEYS,
            shortcut=shortcut,
            season=season,
            matchday=day,
            retrieved_at_utc=str(metadata["retrieved_at_utc"]),
            sha256=str(metadata["sha256"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SnapshotStorageError("archive metadata identity is invalid") from exc


def validate_snapshot_bytes(
    key: str, body: bytes, metadata_bytes: bytes
) -> dict[str, Any]:
    """Verify identity and exact response bytes without rewriting metadata."""
    try:
        metadata = json.loads(metadata_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotStorageError("archive metadata is not valid JSON") from exc
    digest = hashlib.sha256(body).hexdigest()
    if (
        not isinstance(metadata, dict)
        or metadata.get("sha256") != digest
        or type(metadata.get("byte_count")) is not int
        or metadata["byte_count"] != len(body)
        or archive_key(metadata) != key
    ):
        raise SnapshotStorageError("archive snapshot hash, size or identity mismatch")
    return metadata


def check_archive_budget(connection: Any, additional_bytes: int = 0) -> int:
    """Fail closed before an estimated 400 MiB database size; no evidence is deleted."""
    row = connection.execute(
        "SELECT pg_database_size(current_database()) AS database_bytes"
    ).fetchone()
    database_bytes = int(row["database_bytes"])
    if database_bytes + additional_bytes > ARCHIVE_DATABASE_LIMIT_BYTES:
        raise SnapshotStorageError(
            "PostgreSQL archive size guard reached; review database usage and retention"
        )
    return database_bytes


class PostgreSQLSnapshotStore:
    """Use the caller's transaction; never commit, overwrite or delete an archive row."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def _read(self, key: str) -> SnapshotBlob | None:
        row = self.connection.execute(
            """
            SELECT response_bytes, metadata_bytes, response_sha256, metadata_sha256
            FROM public.raw_snapshot_blobs WHERE snapshot_key = %s
            """,
            (key,),
        ).fetchone()
        if row is None:
            return None
        body = bytes(row["response_bytes"])
        metadata_bytes = bytes(row["metadata_bytes"])
        if (
            hashlib.sha256(body).hexdigest() != row["response_sha256"]
            or hashlib.sha256(metadata_bytes).hexdigest() != row["metadata_sha256"]
        ):
            raise SnapshotStorageError("stored PostgreSQL archive hash mismatch")
        metadata = validate_snapshot_bytes(key, body, metadata_bytes)
        return SnapshotBlob(key, body, metadata, metadata_bytes)

    def missing_bytes(self, key: str, body: bytes, metadata_bytes: bytes) -> int:
        """Read-only preview of the missing payload; refuse conflicting immutable bytes."""
        validate_snapshot_bytes(key, body, metadata_bytes)
        existing = self._read(key)
        if existing is None:
            return len(body) + len(metadata_bytes)
        if existing.body != body or existing.metadata_bytes != metadata_bytes:
            raise SnapshotStorageError("immutable PostgreSQL archive content mismatch")
        return 0

    def put_files(
        self,
        key: str,
        body: bytes,
        metadata_bytes: bytes,
        *,
        expected_sha256: str | None = None,
    ) -> None:
        digest = hashlib.sha256(body).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256.lower():
            raise SnapshotStorageError("archive response does not match expected SHA-256")
        additional = self.missing_bytes(key, body, metadata_bytes)
        if additional == 0:
            return
        check_archive_budget(self.connection, additional)
        self.connection.execute(
            """
            INSERT INTO public.raw_snapshot_blobs
                (snapshot_key, response_bytes, metadata_bytes, response_sha256, metadata_sha256)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (snapshot_key) DO NOTHING
            """,
            (key, body, metadata_bytes, digest, hashlib.sha256(metadata_bytes).hexdigest()),
        )
        if self.missing_bytes(key, body, metadata_bytes) != 0:
            raise SnapshotStorageError("PostgreSQL archive read-after-write verification failed")

    def put(self, key: str, body: bytes, metadata: dict[str, object]) -> None:
        metadata_bytes = (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode(
            "utf-8"
        )
        self.put_files(key, body, metadata_bytes)

    def get(self, key: str) -> SnapshotBlob:
        blob = self._read(key)
        if blob is None:
            raise SnapshotStorageError("required PostgreSQL archive snapshot is missing")
        return blob
