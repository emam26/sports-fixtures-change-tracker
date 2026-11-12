"""Read-only inventory and reconciliation of preserved raw snapshots."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class SnapshotAuditError(RuntimeError):
    """Raised when a snapshot inventory cannot be read safely."""


@dataclass(frozen=True)
class SnapshotEntry:
    """The non-secret inventory and validation result for one snapshot directory."""

    directory: Path
    response_path: Path | None
    metadata_path: Path | None
    shortcut: str | None
    season: int | None
    matchday: int | None
    retrieved_at_utc: str | None
    actual_sha256: str | None
    actual_byte_count: int | None
    declared_sha256: str | None
    declared_byte_count: int | None
    status: str
    errors: tuple[str, ...]


@dataclass(frozen=True)
class SnapshotInventory:
    """Deterministic results from scanning a local raw-snapshot directory."""

    root: Path
    entries: tuple[SnapshotEntry, ...]
    duplicate_response_hashes: tuple[tuple[str, tuple[Path, ...]], ...]
    matchday_counts: tuple[tuple[str, int], ...]

    @property
    def corrupt_entries(self) -> tuple[SnapshotEntry, ...]:
        return tuple(entry for entry in self.entries if entry.status == "corrupt")

    @property
    def missing_file_entries(self) -> tuple[SnapshotEntry, ...]:
        return tuple(entry for entry in self.entries if entry.status == "missing-file")

    @property
    def pair_count(self) -> int:
        return sum(
            entry.response_path is not None and entry.metadata_path is not None
            for entry in self.entries
        )


@dataclass(frozen=True)
class SnapshotReference:
    """A source_snapshots row needed for optional database reconciliation."""

    source_snapshot_id: int
    sha256: str
    byte_count: int
    local_directory: Path
    response_path: Path
    metadata_path: Path


@dataclass(frozen=True)
class SnapshotReconciliation:
    """Comparison between local inventory and database-referenced snapshots."""

    referenced_snapshot_ids: tuple[int, ...]
    missing_referenced_snapshot_ids: tuple[int, ...]
    corrupt_referenced_snapshot_ids: tuple[int, ...]
    path_mismatches: tuple[int, ...]
    hash_or_size_mismatches: tuple[int, ...]
    unreferenced_local_directories: tuple[Path, ...]
    unresolved: tuple[str, ...]

    @property
    def has_failure(self) -> bool:
        return bool(
            self.missing_referenced_snapshot_ids
            or self.corrupt_referenced_snapshot_ids
            or self.path_mismatches
            or self.hash_or_size_mismatches
            or self.unresolved
        )


def _path_key(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False)).casefold()


def _metadata_identity(metadata: dict[str, Any]) -> tuple[str | None, int | None, int | None]:
    shortcut = metadata.get("shortcut")
    season = metadata.get("season")
    matchday = metadata.get("matchday")
    try:
        season_value = int(season) if season is not None else None
    except (TypeError, ValueError):
        season_value = None
    try:
        matchday_value = int(matchday) if matchday is not None else None
    except (TypeError, ValueError):
        matchday_value = None
    return (
        str(shortcut) if shortcut is not None else None,
        season_value,
        matchday_value,
    )


def _path_identity(root: Path, directory: Path) -> tuple[str | None, int | None, int | None]:
    try:
        parts = directory.resolve(strict=False).relative_to(root.resolve(strict=False)).parts
    except ValueError:
        return None, None, None
    if len(parts) < 4 or not parts[-2].startswith("matchday-"):
        return None, None, None
    try:
        season = int(parts[-3])
        matchday = int(parts[-2].removeprefix("matchday-"))
    except ValueError:
        return parts[-4], None, None
    return parts[-4], season, matchday


def _validate_entry(root: Path, directory: Path) -> SnapshotEntry:
    response_path = directory / "response.json"
    metadata_path = directory / "metadata.json"
    errors: list[str] = []
    actual_sha256: str | None = None
    actual_byte_count: int | None = None
    declared_sha256: str | None = None
    declared_byte_count: int | None = None
    metadata: dict[str, Any] | None = None

    if not response_path.is_file():
        errors.append("response.json is missing")
    else:
        try:
            body = response_path.read_bytes()
            actual_byte_count = len(body)
            actual_sha256 = hashlib.sha256(body).hexdigest()
            try:
                decoded = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                errors.append("response.json is not valid JSON")
            else:
                if not isinstance(decoded, list):
                    errors.append("response.json top level is not a list")
        except OSError:
            errors.append("response.json could not be read")

    if not metadata_path.is_file():
        errors.append("metadata.json is missing")
    else:
        try:
            metadata = json.loads(metadata_path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append("metadata.json is not valid JSON")
        else:
            if not isinstance(metadata, dict):
                errors.append("metadata.json top level is not an object")
                metadata = None

    shortcut: str | None = None
    season: int | None = None
    matchday: int | None = None
    retrieved_at_utc: str | None = None
    if metadata is not None:
        required_fields = {
            "provider",
            "url",
            "shortcut",
            "season",
            "matchday",
            "retrieved_at_utc",
            "http_status",
            "content_type",
            "byte_count",
            "sha256",
        }
        missing_fields = sorted(required_fields - set(metadata))
        if missing_fields:
            errors.append("metadata fields missing: " + ", ".join(missing_fields))
        shortcut, season, matchday = _metadata_identity(metadata)
        raw_retrieved = metadata.get("retrieved_at_utc")
        retrieved_at_utc = str(raw_retrieved) if raw_retrieved is not None else None
        raw_sha256 = metadata.get("sha256")
        declared_sha256 = str(raw_sha256).lower() if raw_sha256 is not None else None
        if actual_sha256 is not None:
            if declared_sha256 != actual_sha256:
                errors.append("metadata SHA-256 does not match response bytes")
        try:
            declared_byte_count = int(metadata.get("byte_count"))
        except (TypeError, ValueError):
            errors.append("metadata byte_count is invalid")
        else:
            if actual_byte_count is not None and declared_byte_count != actual_byte_count:
                errors.append("metadata byte_count does not match response bytes")

        path_shortcut, path_season, path_matchday = _path_identity(root, directory)
        if path_shortcut is None:
            errors.append("snapshot path does not contain shortcut, season and matchday")
        elif (shortcut, season, matchday) != (
            path_shortcut,
            path_season,
            path_matchday,
        ):
            errors.append("metadata identity does not match snapshot path")

    status = "valid"
    if not response_path.is_file() or not metadata_path.is_file():
        status = "missing-file"
    elif errors:
        status = "corrupt"

    return SnapshotEntry(
        directory=directory,
        response_path=response_path if response_path.is_file() else None,
        metadata_path=metadata_path if metadata_path.is_file() else None,
        shortcut=shortcut,
        season=season,
        matchday=matchday,
        retrieved_at_utc=retrieved_at_utc,
        actual_sha256=actual_sha256,
        actual_byte_count=actual_byte_count,
        declared_sha256=declared_sha256,
        declared_byte_count=declared_byte_count,
        status=status,
        errors=tuple(errors),
    )


def scan_snapshot_directory(root: Path) -> SnapshotInventory:
    """Scan local files without opening a database, cloud store, or network."""

    root = root.expanduser().resolve(strict=False)
    if not root.is_dir():
        raise SnapshotAuditError(f"snapshot root is not a directory: {root}")
    directories = {path.parent for path in root.rglob("response.json")} | {
        path.parent for path in root.rglob("metadata.json")
    }
    entries = tuple(
        _validate_entry(root, directory) for directory in sorted(directories, key=_path_key)
    )
    hash_groups: dict[str, list[Path]] = defaultdict(list)
    for entry in entries:
        if entry.actual_sha256 is not None:
            hash_groups[entry.actual_sha256].append(entry.directory)
    duplicate_hashes = tuple(
        (digest, tuple(sorted(paths, key=_path_key)))
        for digest, paths in sorted(hash_groups.items())
        if len(paths) > 1
    )
    matchday_groups: dict[str, int] = defaultdict(int)
    for entry in entries:
        label = str(entry.matchday) if entry.matchday is not None else "unknown"
        matchday_groups[label] += 1
    return SnapshotInventory(
        root=root,
        entries=entries,
        duplicate_response_hashes=duplicate_hashes,
        matchday_counts=tuple(sorted(matchday_groups.items())),
    )


def _row_value(row: Any, key: str, index: int) -> Any:
    return row[key] if isinstance(row, dict) else row[index]


def load_sqlserver_snapshot_references(connection: Any) -> tuple[SnapshotReference, ...]:
    """Load only snapshot metadata needed for an optional read-only reconciliation."""

    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT source_snapshot_id, sha256, byte_count,
               local_directory, response_path, metadata_path
        FROM dbo.source_snapshots
        ORDER BY source_snapshot_id
        """
    )
    references = []
    for row in cursor.fetchall():
        references.append(
            SnapshotReference(
                source_snapshot_id=int(_row_value(row, "source_snapshot_id", 0)),
                sha256=str(_row_value(row, "sha256", 1)).lower(),
                byte_count=int(_row_value(row, "byte_count", 2)),
                local_directory=Path(str(_row_value(row, "local_directory", 3))),
                response_path=Path(str(_row_value(row, "response_path", 4))),
                metadata_path=Path(str(_row_value(row, "metadata_path", 5))),
            )
        )
    return tuple(references)


def reconcile_snapshot_references(
    inventory: SnapshotInventory,
    references: tuple[SnapshotReference, ...],
) -> SnapshotReconciliation:
    """Compare local evidence to DB references without modifying either side."""

    entries_by_path = {_path_key(entry.directory): entry for entry in inventory.entries}
    referenced_paths: set[str] = set()
    missing: list[int] = []
    corrupt: list[int] = []
    path_mismatches: list[int] = []
    hash_or_size_mismatches: list[int] = []
    unresolved: list[str] = []

    for reference in references:
        reference_directory = reference.local_directory.expanduser().resolve(strict=False)
        reference_key = _path_key(reference_directory)
        referenced_paths.add(reference_key)
        entry = entries_by_path.get(reference_key)
        if entry is None:
            missing.append(reference.source_snapshot_id)
            continue
        if entry.status != "valid":
            corrupt.append(reference.source_snapshot_id)
        expected_response = reference_directory / "response.json"
        expected_metadata = reference_directory / "metadata.json"
        if _path_key(reference.response_path) != _path_key(expected_response) or (
            _path_key(reference.metadata_path) != _path_key(expected_metadata)
        ):
            path_mismatches.append(reference.source_snapshot_id)
        if (
            entry.actual_sha256 != reference.sha256
            or entry.actual_byte_count != reference.byte_count
        ):
            hash_or_size_mismatches.append(reference.source_snapshot_id)
        if entry.errors:
            unresolved.extend(
                f"snapshot {reference.source_snapshot_id}: {error}" for error in entry.errors
            )

    unreferenced = tuple(
        sorted(
            (
                entry.directory
                for entry in inventory.entries
                if _path_key(entry.directory) not in referenced_paths
            ),
            key=_path_key,
        )
    )
    return SnapshotReconciliation(
        referenced_snapshot_ids=tuple(reference.source_snapshot_id for reference in references),
        missing_referenced_snapshot_ids=tuple(sorted(missing)),
        corrupt_referenced_snapshot_ids=tuple(sorted(corrupt)),
        path_mismatches=tuple(sorted(path_mismatches)),
        hash_or_size_mismatches=tuple(sorted(hash_or_size_mismatches)),
        unreferenced_local_directories=unreferenced,
        unresolved=tuple(sorted(set(unresolved))),
    )


def inventory_as_dict(
    inventory: SnapshotInventory,
    reconciliation: SnapshotReconciliation | None = None,
) -> dict[str, Any]:
    """Return a JSON-safe report without response bytes or credential-bearing data."""

    result: dict[str, Any] = {
        "root": str(inventory.root),
        "snapshot_pair_count": inventory.pair_count,
        "entry_count": len(inventory.entries),
        "duplicate_response_hashes": [
            {"sha256": digest, "directories": [str(path) for path in paths]}
            for digest, paths in inventory.duplicate_response_hashes
        ],
        "matchday_counts": dict(inventory.matchday_counts),
        "entries": [
            {
                **asdict(entry),
                "directory": str(entry.directory),
                "response_path": str(entry.response_path) if entry.response_path else None,
                "metadata_path": str(entry.metadata_path) if entry.metadata_path else None,
                "errors": list(entry.errors),
            }
            for entry in inventory.entries
        ],
    }
    if reconciliation is not None:
        result["reconciliation"] = {
            "referenced_snapshot_ids": list(reconciliation.referenced_snapshot_ids),
            "missing_referenced_snapshot_ids": list(reconciliation.missing_referenced_snapshot_ids),
            "corrupt_referenced_snapshot_ids": list(reconciliation.corrupt_referenced_snapshot_ids),
            "path_mismatches": list(reconciliation.path_mismatches),
            "hash_or_size_mismatches": list(reconciliation.hash_or_size_mismatches),
            "unreferenced_local_directories": [
                str(path) for path in reconciliation.unreferenced_local_directories
            ],
            "unresolved": list(reconciliation.unresolved),
        }
    return result
