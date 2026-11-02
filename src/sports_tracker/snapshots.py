"""Immutable raw snapshot storage for validated OpenLigaDB responses."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import OpenLigaDBSettings
from .openligadb import OpenLigaDBResponse


class SnapshotAlreadyExistsError(FileExistsError):
    """Raised when a snapshot directory already exists."""


@dataclass(frozen=True)
class RawSnapshot:
    """Paths and metadata for one immutable raw response snapshot."""

    directory: Path
    response_path: Path
    metadata_path: Path
    sha256: str
    metadata: dict[str, object]


def _timestamp_for_directory(retrieved_at_utc: str) -> str:
    parsed = datetime.fromisoformat(retrieved_at_utc.replace("Z", "+00:00"))
    return parsed.astimezone(UTC).strftime("%Y%m%dT%H%M%S.%fZ")


def save_raw_snapshot(
    response: OpenLigaDBResponse,
    settings: OpenLigaDBSettings,
    matchday: int,
) -> RawSnapshot:
    """Write exact response bytes and metadata without overwriting existing files."""

    digest = hashlib.sha256(response.body).hexdigest()
    directory_name = f"{_timestamp_for_directory(response.retrieved_at_utc)}_{digest}"
    directory = (
        settings.raw_snapshot_directory
        / settings.shortcut
        / str(settings.season)
        / f"matchday-{matchday}"
        / directory_name
    )
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise SnapshotAlreadyExistsError(f"Raw snapshot already exists: {directory}") from exc

    metadata: dict[str, object] = {
        "provider": "OpenLigaDB",
        "url": response.url,
        "shortcut": settings.shortcut,
        "season": settings.season,
        "matchday": matchday,
        "retrieved_at_utc": response.retrieved_at_utc,
        "http_status": response.status_code,
        "content_type": response.content_type,
        "byte_count": len(response.body),
        "sha256": digest,
    }
    response_path = directory / "response.json"
    metadata_path = directory / "metadata.json"
    try:
        with response_path.open("xb") as response_file:
            response_file.write(response.body)
        with metadata_path.open("x", encoding="utf-8", newline="\n") as metadata_file:
            json.dump(metadata, metadata_file, indent=2, ensure_ascii=False)
            metadata_file.write("\n")
    except FileExistsError as exc:
        raise SnapshotAlreadyExistsError(f"Raw snapshot file already exists: {directory}") from exc

    return RawSnapshot(
        directory=directory,
        response_path=response_path,
        metadata_path=metadata_path,
        sha256=digest,
        metadata=metadata,
    )
