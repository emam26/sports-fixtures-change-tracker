from sports_tracker.postgres_preflight import REQUIRED_TABLES, build_preflight_report


def test_preflight_report_fails_when_required_table_is_missing() -> None:
    presence = {table: True for table in REQUIRED_TABLES}
    presence["match_goals"] = False

    report = build_preflight_report("tracker", "readonly", presence)

    assert report["status"] == "FAIL"
    assert report["missing_tables"] == ["match_goals"]


def test_preflight_report_does_not_include_connection_details() -> None:
    report = build_preflight_report(
        "tracker",
        "sports_tracker_api",
        {table: True for table in REQUIRED_TABLES},
    )

    assert report["status"] == "PASS"
    assert "password" not in str(report).lower()
