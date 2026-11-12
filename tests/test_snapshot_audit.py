from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sports_tracker.snapshot_audit import (
    SnapshotReference,
    load_sqlserver_snapshot_references,
    reconcile_snapshot_references,
    scan_snapshot_directory,
)


def _write_pair(
    root: Path,
    *,
    matchday: int,
    name: str,
    body: bytes,
    shortcut: str = "ucl",
    season: int = 2026,
    byte_count: int | None = None,
    sha256: str | None = None,
) -> Path:
    directory = root / shortcut / str(season) / f"matchday-{matchday}" / name
    directory.mkdir(parents=True)
    (directory / "response.json").write_bytes(body)
    metadata = {
        "provider": "OpenLigaDB",
        "url": f"https://api.openligadb.de/getmatchdata/{shortcut}/{season}/{matchday}",
        "shortcut": shortcut,
        "season": season,
        "matchday": matchday,
        "retrieved_at_utc": "2026-11-12T00:00:00Z",
        "http_status": 200,
        "content_type": "application/json",
        "byte_count": len(body) if byte_count is None else byte_count,
        "sha256": hashlib.sha256(body).hexdigest() if sha256 is None else sha256,
    }
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return directory


def test_inventory_keeps_identical_retrievals_distinct(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    for index in range(17):
        body = b'[{"matchID": 1}]' if index < 2 else f"[{index}]".encode()
        _write_pair(root, matchday=1 if index < 9 else 2, name=f"capture-{index}", body=body)

    report = scan_snapshot_directory(root)

    assert len(report.entries) == 17
    assert sum(entry.status == "valid" for entry in report.entries) == 17
    assert len(report.duplicate_response_hashes) == 1
    assert len(report.duplicate_response_hashes[0][1]) == 2
    assert dict(report.matchday_counts) == {"1": 9, "2": 8}


def test_inventory_reports_missing_files_malformed_metadata_and_corruption(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    missing_response = root / "ucl" / "2026" / "matchday-1" / "missing-response"
    missing_response.mkdir(parents=True)
    (missing_response / "metadata.json").write_text("{}", encoding="utf-8")
    missing_metadata = root / "ucl" / "2026" / "matchday-1" / "missing-metadata"
    missing_metadata.mkdir(parents=True)
    (missing_metadata / "response.json").write_bytes(b"[]")
    malformed = root / "ucl" / "2026" / "matchday-1" / "malformed"
    malformed.mkdir(parents=True)
    (malformed / "response.json").write_bytes(b"[]")
    (malformed / "metadata.json").write_text("not-json", encoding="utf-8")
    _write_pair(root, matchday=1, name="bad-size", body=b"[]", byte_count=99)

    report = scan_snapshot_directory(root)
    statuses = {entry.directory.name: entry.status for entry in report.entries}

    assert statuses["missing-response"] == "missing-file"
    assert statuses["missing-metadata"] == "missing-file"
    assert statuses["malformed"] == "corrupt"
    assert statuses["bad-size"] == "corrupt"
    assert any("byte_count" in error for entry in report.entries for error in entry.errors)


def test_inventory_detects_identity_path_mismatch_and_bad_response_json(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    path_mismatch = _write_pair(root, matchday=1, name="identity", body=b"[]")
    metadata_path = path_mismatch / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["matchday"] = 2
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    _write_pair(root, matchday=1, name="bad-json", body=b"not-json")

    report = scan_snapshot_directory(root)

    assert all(entry.status == "corrupt" for entry in report.entries)
    assert any("identity" in error for entry in report.entries for error in entry.errors)
    assert any("not valid JSON" in error for entry in report.entries for error in entry.errors)


class _ReferenceCursor:
    def execute(self, statement: str) -> None:
        assert "FROM dbo.source_snapshots" in statement

    def fetchall(self) -> list[tuple[object, ...]]:
        return [(7, "a" * 64, 2, "data/raw/ucl/2026/matchday-1/capture", "response", "metadata")]


class _ReferenceConnection:
    def cursor(self) -> _ReferenceCursor:
        return _ReferenceCursor()


def test_optional_sql_reference_loading_and_reconciliation_are_read_only(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    local = _write_pair(root, matchday=1, name="capture", body=b"[]")
    report = scan_snapshot_directory(root)
    reference = SnapshotReference(
        source_snapshot_id=7,
        sha256=hashlib.sha256(b"[]").hexdigest(),
        byte_count=2,
        local_directory=local,
        response_path=local / "response.json",
        metadata_path=local / "metadata.json",
    )

    reconciliation = reconcile_snapshot_references(report, (reference,))

    assert not reconciliation.has_failure
    assert reconciliation.unreferenced_local_directories == ()
    assert (local / "response.json").read_bytes() == b"[]"


def test_reconciliation_distinguishes_missing_references_and_unreferenced_local(
    tmp_path: Path,
) -> None:
    root = tmp_path / "raw"
    local = _write_pair(root, matchday=1, name="local-only", body=b"[]")
    report = scan_snapshot_directory(root)
    missing = SnapshotReference(
        source_snapshot_id=8,
        sha256="b" * 64,
        byte_count=2,
        local_directory=root / "ucl" / "2026" / "matchday-2" / "missing",
        response_path=root / "ucl" / "2026" / "matchday-2" / "missing" / "response.json",
        metadata_path=root / "ucl" / "2026" / "matchday-2" / "missing" / "metadata.json",
    )

    reconciliation = reconcile_snapshot_references(report, (missing,))

    assert reconciliation.missing_referenced_snapshot_ids == (8,)
    assert reconciliation.unreferenced_local_directories == (local,)


def test_reconciliation_reports_path_hash_and_size_mismatches(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    local = _write_pair(root, matchday=1, name="capture", body=b"[]")
    report = scan_snapshot_directory(root)
    reference = SnapshotReference(
        source_snapshot_id=9,
        sha256="c" * 64,
        byte_count=99,
        local_directory=local,
        response_path=local / "wrong-response.json",
        metadata_path=local / "metadata.json",
    )

    reconciliation = reconcile_snapshot_references(report, (reference,))

    assert reconciliation.path_mismatches == (9,)
    assert reconciliation.hash_or_size_mismatches == (9,)
    assert reconciliation.has_failure


def test_reference_loader_reads_only_snapshot_metadata() -> None:
    references = load_sqlserver_snapshot_references(_ReferenceConnection())

    assert references[0].source_snapshot_id == 7
    assert references[0].sha256 == "a" * 64
