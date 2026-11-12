from datetime import UTC, datetime, timedelta

from sports_tracker.postgres_parity import compare_table


def test_parity_maps_rowversion_to_preserved_source_bytes():
    source_rows = [
        {
            "sync_checkpoint_id": 1,
            "checkpoint_version": b"\x01\x02",
            "matchday": 3,
        }
    ]
    target_rows = [
        {
            "sync_checkpoint_id": 1,
            "checkpoint_version": 0,
            "source_checkpoint_version": b"\x01\x02",
            "matchday": 3,
        }
    ]
    source_columns = ("sync_checkpoint_id", "checkpoint_version", "matchday")
    target_columns = source_columns + ("source_checkpoint_version",)

    report = compare_table(
        "sync_checkpoints",
        source_columns,
        source_rows,
        target_columns,
        target_rows,
    )

    assert report["status"] == "MATCH"
    assert report["transformation_mapping"]


def test_parity_detects_changed_preserved_rowversion_bytes():
    source_rows = [
        {
            "sync_checkpoint_id": 1,
            "checkpoint_version": b"\x01\x02",
            "matchday": 3,
        }
    ]
    target_rows = [
        {
            "sync_checkpoint_id": 1,
            "checkpoint_version": 0,
            "source_checkpoint_version": b"\x01\x03",
            "matchday": 3,
        }
    ]
    source_columns = ("sync_checkpoint_id", "checkpoint_version", "matchday")
    target_columns = source_columns + ("source_checkpoint_version",)

    report = compare_table(
        "sync_checkpoints",
        source_columns,
        source_rows,
        target_columns,
        target_rows,
    )

    assert report["status"] == "MISMATCH"
    assert any(
        "checkpoint_version -> source_checkpoint_version" in difference["changes"]
        for difference in report["row_differences"]
    )


def test_parity_rejects_missing_checkpoint_mapping_and_invalid_version():
    source_rows = [
        {
            "sync_checkpoint_id": 1,
            "checkpoint_version": b"\x01\x02",
            "matchday": 3,
        }
    ]
    target_rows = [
        {
            "sync_checkpoint_id": 1,
            "checkpoint_version": -1,
            "matchday": 3,
        }
    ]
    columns = ("sync_checkpoint_id", "checkpoint_version", "matchday")

    report = compare_table(
        "sync_checkpoints",
        columns,
        source_rows,
        columns,
        target_rows,
    )

    assert report["status"] == "MISMATCH"
    assert report["schema_difference"]
    assert report["application_invariant_violations"]


def test_parity_keeps_unexpected_schema_changes_visible():
    source_rows = [{"match_id": 10, "status": "finished"}]
    target_rows = [{"match_id": 10, "status": "finished", "unexpected_column": "value"}]

    report = compare_table(
        "matches",
        ("match_id", "status"),
        source_rows,
        ("match_id", "status", "unexpected_column"),
        target_rows,
    )

    assert report["status"] == "MISMATCH"
    assert "unexpected_column" in report["schema_difference"]


def test_parity_detects_different_utc_instants():
    source_rows = [{"match_id": 10, "kickoff_utc": datetime(2026, 11, 2, 10, 0, tzinfo=UTC)}]
    target_rows = [
        {
            "match_id": 10,
            "kickoff_utc": datetime(2026, 11, 2, 10, 0, tzinfo=UTC) + timedelta(seconds=1),
        }
    ]

    report = compare_table(
        "matches",
        ("match_id", "kickoff_utc"),
        source_rows,
        ("match_id", "kickoff_utc"),
        target_rows,
    )

    assert report["status"] == "MISMATCH"
    assert report["row_differences"]


def test_parity_detects_microsecond_timestamp_differences():
    source_rows = [
        {
            "match_id": 10,
            "kickoff_utc": datetime(2026, 11, 2, 10, 0, 0, 123456),
        }
    ]
    target_rows = [
        {
            "match_id": 10,
            "kickoff_utc": datetime(2026, 11, 2, 10, 0, 0, 123457, tzinfo=UTC),
        }
    ]

    report = compare_table(
        "matches",
        ("match_id", "kickoff_utc"),
        source_rows,
        ("match_id", "kickoff_utc"),
        target_rows,
    )

    assert report["status"] == "MISMATCH"
    assert report["row_differences"]


def test_parity_reports_identical_rows_as_match() -> None:
    rows = [{"match_id": 10, "status": "finished"}]

    report = compare_table(
        "matches",
        ("match_id", "status"),
        rows,
        ("match_id", "status"),
        rows,
    )

    assert report["status"] == "MATCH"


def test_parity_reports_timezone_metadata_as_a_mismatch() -> None:
    source_rows = [
        {
            "match_id": 10,
            "kickoff_utc": datetime(2026, 11, 2, 10, 0, 0, 123456),
        }
    ]
    target_rows = [
        {
            "match_id": 10,
            "kickoff_utc": datetime(2026, 11, 2, 10, 0, 0, 123456, tzinfo=UTC),
        }
    ]

    report = compare_table(
        "matches",
        ("match_id", "kickoff_utc"),
        source_rows,
        ("match_id", "kickoff_utc"),
        target_rows,
    )

    assert report["status"] == "MATCH"
    assert not report["row_differences"]


def test_parity_distinguishes_missing_rows_from_field_mismatches() -> None:
    source_rows = [{"match_id": 10, "status": "finished"}]
    target_rows = [{"match_id": 10, "status": "scheduled"}, {"match_id": 11}]

    report = compare_table(
        "matches",
        ("match_id", "status"),
        source_rows,
        ("match_id", "status"),
        target_rows,
    )

    assert report["status"] == "MISSING"
    assert report["target_only_keys"]
    assert report["row_differences"]


def test_parity_reports_duplicate_stable_keys() -> None:
    rows = [
        {"match_id": 10, "status": "finished"},
        {"match_id": 10, "status": "finished"},
    ]

    report = compare_table(
        "matches",
        ("match_id", "status"),
        rows,
        ("match_id", "status"),
        rows[:1],
    )

    assert report["status"] == "MISMATCH"
    assert report["source_duplicate_keys"]
