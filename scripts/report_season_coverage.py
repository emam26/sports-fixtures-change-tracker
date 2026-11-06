"""Report configured league-phase coverage from immutable local OpenLigaDB snapshots."""

from __future__ import annotations

import argparse

from sports_tracker.config import ConfigurationError, load_openligadb_settings
from sports_tracker.season_coverage import collect_season_coverage


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main() -> int:
    build_parser().parse_args()
    try:
        settings = load_openligadb_settings()
        report = collect_season_coverage(settings)
    except ConfigurationError as exc:
        print(f"Season coverage report failed: {exc}")
        return 2

    expected_matchdays = ", ".join(str(matchday) for matchday in report.expected_matchdays)
    print(f"Competition: {settings.shortcut} / {settings.season}")
    print(f"Expected league-phase matchdays: {expected_matchdays}")
    print(
        "Expected fixtures: "
        f"{report.expected_fixture_count} "
        f"({len(report.expected_matchdays)} matchdays x "
        f"{report.expected_fixtures_per_matchday} fixtures)"
    )
    print("Raw source-capture coverage:")
    for matchday in report.matchdays:
        print(
            f"  Matchday {matchday.matchday}: {matchday.state}; "
            f"{matchday.retrieved_fixture_count}/"
            f"{matchday.expected_fixture_count} unique fixtures; "
            f"{matchday.valid_snapshot_count}/{matchday.snapshot_count} valid snapshots"
        )
        for error in matchday.errors:
            print(f"    Capture validation: {error}")
    print(f"Unique provider fixture IDs retrieved: {report.retrieved_fixture_count}")
    if report.additional_local_matchdays:
        print(
            "Additional locally captured matchdays pending explicit scope review: "
            + ", ".join(str(matchday) for matchday in report.additional_local_matchdays)
        )
    if report.duplicate_provider_match_ids:
        print(
            "Cross-matchday provider match IDs require investigation: "
            + ", ".join(str(identifier) for identifier in report.duplicate_provider_match_ids)
        )
    print(
        "Interpretation: not-captured is a local capture gap, not proof that OpenLigaDB "
        "lacks the fixture. This report does not claim a database import succeeded."
    )
    return 0 if report.capture_is_complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
