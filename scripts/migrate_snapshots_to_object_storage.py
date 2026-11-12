"""Preview or apply migration of preserved raw snapshots to private object storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sports_tracker.config import (
    ConfigurationError,
    load_database_settings,
    load_object_storage_settings,
    load_postgresql_settings,
)
from sports_tracker.database import database_connection
from sports_tracker.postgres import postgresql_connection
from sports_tracker.storage import NeonS3SnapshotStore, build_snapshot_object_key


class SnapshotMigrationError(RuntimeError):
    """Raised when a local snapshot cannot be reconciled safely."""


def _validated_schema(schema: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema) is None:
        raise SnapshotMigrationError("PostgreSQL schema must be a simple SQL identifier")
    return schema


@dataclass(frozen=True)
class SnapshotTransfer:
    source_snapshot_id: int
    old_local_directory: str
    object_key: str
    body: bytes
    metadata_bytes: bytes
    sha256: str


def _row_value(row: Any, key: str, index: int) -> Any:
    return row[key] if isinstance(row, Mapping) else row[index]


def _utc_text(value: Any) -> str:
    if isinstance(value, datetime):
        timestamp = value if value.tzinfo else value.replace(tzinfo=UTC)
        return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value)


def _read_transfer(row: Any, object_settings: Any) -> SnapshotTransfer:
    snapshot_id = int(row[0])
    provider = str(row[1])
    shortcut = str(row[2])
    season = int(row[4])
    matchday = int(row[5])
    source_url = str(row[6])
    retrieved_at = _utc_text(row[7])
    http_status = int(row[8])
    content_type = row[9]
    byte_count = int(row[10])
    expected_sha = str(row[11]).lower()
    old_local_directory = str(row[12])
    response_path = Path(str(row[13]))
    metadata_path = Path(str(row[14]))
    try:
        body = response_path.read_bytes()
        metadata_bytes = metadata_path.read_bytes()
    except OSError as exc:
        raise SnapshotMigrationError(
            f"snapshot {snapshot_id} references missing local files"
        ) from exc
    digest = hashlib.sha256(body).hexdigest()
    if len(body) != byte_count or digest != expected_sha:
        raise SnapshotMigrationError(
            f"snapshot {snapshot_id} response bytes do not match database metadata"
        )
    try:
        metadata = json.loads(metadata_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotMigrationError(f"snapshot {snapshot_id} metadata is invalid JSON") from exc
    if not isinstance(metadata, dict):
        raise SnapshotMigrationError(f"snapshot {snapshot_id} metadata is not an object")
    expected_values = {
        "provider": provider,
        "shortcut": shortcut,
        "season": season,
        "matchday": matchday,
        "url": source_url,
        "http_status": http_status,
        "byte_count": byte_count,
        "sha256": expected_sha,
    }
    for field, expected in expected_values.items():
        actual = metadata.get(field)
        if str(actual).lower() != str(expected).lower():
            raise SnapshotMigrationError(
                f"snapshot {snapshot_id} metadata field {field} is unreconciled"
            )
    if _utc_text(metadata.get("retrieved_at_utc")) != retrieved_at:
        raise SnapshotMigrationError(f"snapshot {snapshot_id} retrieval timestamp is unreconciled")
    if content_type is not None and metadata.get("content_type") != content_type:
        raise SnapshotMigrationError(f"snapshot {snapshot_id} content type is unreconciled")
    key = build_snapshot_object_key(
        object_settings,
        shortcut=shortcut,
        season=season,
        matchday=matchday,
        retrieved_at_utc=retrieved_at,
        sha256=expected_sha,
    )
    return SnapshotTransfer(
        source_snapshot_id=snapshot_id,
        old_local_directory=old_local_directory,
        object_key=key,
        body=body,
        metadata_bytes=metadata_bytes,
        sha256=expected_sha,
    )


def _load_transfers(object_settings: Any) -> list[SnapshotTransfer]:
    with database_connection(load_database_settings()) as source:
        cursor = source.cursor()
        cursor.execute(
            """
            SELECT source_snapshot_id, provider, provider_shortcut,
                   source_league_id, season_start_year, matchday_number,
                   source_url, retrieved_at_utc, http_status, content_type,
                   byte_count, sha256, local_directory, response_path,
                   metadata_path
            FROM dbo.source_snapshots
            ORDER BY source_snapshot_id
            """
        )
        return [_read_transfer(row, object_settings) for row in cursor.fetchall()]


def _verify_target_references(
    connection: Any,
    transfers: list[SnapshotTransfer],
    schema: str,
) -> None:
    for transfer in transfers:
        cursor = connection.cursor()
        cursor.execute(
            f"SELECT sha256, local_directory, response_path, metadata_path "
            f'FROM "{schema}"."source_snapshots" '
            "WHERE source_snapshot_id = %s",
            (transfer.source_snapshot_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise SnapshotMigrationError(
                f"PostgreSQL is missing source snapshot {transfer.source_snapshot_id}"
            )
        if str(_row_value(row, "sha256", 0)).lower() != transfer.sha256:
            raise SnapshotMigrationError(
                f"PostgreSQL source snapshot {transfer.source_snapshot_id} has a hash mismatch"
            )
        if str(_row_value(row, "local_directory", 1)) not in {
            transfer.old_local_directory,
            transfer.object_key,
        }:
            raise SnapshotMigrationError(
                f"PostgreSQL source snapshot {transfer.source_snapshot_id} has an "
                "unexpected locator"
            )


def migrate_snapshots(*, apply: bool, schema: str = "public") -> int:
    schema = _validated_schema(schema)
    object_settings = load_object_storage_settings()
    transfers = _load_transfers(object_settings)
    with postgresql_connection(load_postgresql_settings()) as target:
        try:
            _verify_target_references(target, transfers, schema)
            if not apply:
                target.rollback()
                return len(transfers)
            store = NeonS3SnapshotStore(object_settings)
            for transfer in transfers:
                store.put_files(
                    transfer.object_key,
                    transfer.body,
                    transfer.metadata_bytes,
                    expected_sha256=transfer.sha256,
                )
            cursor = target.cursor()
            for transfer in transfers:
                cursor.execute(
                    f'UPDATE "{schema}"."source_snapshots" '
                    "SET local_directory = %s, response_path = %s, metadata_path = %s "
                    "WHERE source_snapshot_id = %s AND sha256 = %s",
                    (
                        transfer.object_key,
                        f"{transfer.object_key}/response.json",
                        f"{transfer.object_key}/metadata.json",
                        transfer.source_snapshot_id,
                        transfer.sha256,
                    ),
                )
                if cursor.rowcount != 1:
                    raise SnapshotMigrationError(
                        f"could not update PostgreSQL source snapshot {transfer.source_snapshot_id}"
                    )
            target.commit()
        except Exception:
            target.rollback()
            raise
    return len(transfers)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="upload verified snapshots and update PostgreSQL locators",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        count = migrate_snapshots(apply=args.apply, schema=load_postgresql_settings().schema)
    except (ConfigurationError, OSError, SnapshotMigrationError, RuntimeError) as exc:
        print(f"Snapshot migration stopped safely: {type(exc).__name__}: {exc}")
        return 1
    mode = "applied" if args.apply else "previewed"
    print(f"Snapshot migration {mode}; verified {count} snapshots.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
