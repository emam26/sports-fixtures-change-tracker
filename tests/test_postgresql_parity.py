from datetime import UTC, datetime

from sports_tracker.postgres_parity import compare_table


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

    assert report["status"] == "MISMATCH"
    assert report["row_differences"]


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
