from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sports_tracker.config import OpenLigaDBSettings
from sports_tracker.season_coverage import collect_season_coverage


def _settings(tmp_path: Path) -> OpenLigaDBSettings:
    return OpenLigaDBSettings(
        base_url="https://api.openligadb.de",
        shortcut="ucl",
        season=2026,
        expected_league_id=4946,
        timeout_seconds=10.0,
        raw_snapshot_directory=tmp_path / "data" / "raw",
        expected_league_phase_matchdays=(1, 2),
        expected_fixtures_per_matchday=2,
    )


def _write_snapshot(
    settings: OpenLigaDBSettings,
    *,
    matchday: int,
    match_ids: tuple[int, ...],
    directory_name: str,
    league_id: int = 4946,
) -> Path:
    records = [
        {
            "matchID": provider_match_id,
            "leagueShortcut": settings.shortcut,
            "leagueSeason": settings.season,
            "leagueId": league_id,
        }
        for provider_match_id in match_ids
    ]
    body = json.dumps(records, separators=(",", ":")).encode("utf-8")
    directory = (
        settings.raw_snapshot_directory
        / settings.shortcut
        / str(settings.season)
        / f"matchday-{matchday}"
        / directory_name
    )
    directory.mkdir(parents=True)
    (directory / "response.json").write_bytes(body)
    (directory / "metadata.json").write_text(
        json.dumps(
            {
                "provider": "OpenLigaDB",
                "url": f"https://api.openligadb.de/getmatchdata/ucl/2026/{matchday}",
                "shortcut": settings.shortcut,
                "season": settings.season,
                "matchday": matchday,
                "byte_count": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return directory


def test_coverage_reports_missing_matchdays_without_claiming_source_unavailability(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    _write_snapshot(settings, matchday=1, match_ids=(101, 102), directory_name="first")
    _write_snapshot(settings, matchday=1, match_ids=(101, 102), directory_name="replay")

    report = collect_season_coverage(settings)

    assert report.expected_fixture_count == 4
    assert report.retrieved_fixture_count == 2
    assert report.matchdays[0].state == "captured-complete"
    assert report.matchdays[0].snapshot_count == 2
    assert report.matchdays[0].retrieved_fixture_count == 2
    assert report.matchdays[1].state == "not-captured"
    assert report.missing_matchdays == (2,)
    assert report.capture_is_complete is False


def test_coverage_marks_invalid_capture_separately_from_missing_source_data(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_snapshot(
        settings,
        matchday=1,
        match_ids=(101, 102),
        directory_name="invalid-identity",
        league_id=9999,
    )

    report = collect_season_coverage(settings)

    assert report.matchdays[0].state == "invalid-capture"
    assert report.matchdays[0].invalid_snapshot_count == 1
    assert "unexpected competition identity" in report.matchdays[0].errors[0]
    assert report.matchdays[1].state == "not-captured"


def test_coverage_detects_provider_fixture_ids_reused_across_matchdays(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_snapshot(settings, matchday=1, match_ids=(101, 102), directory_name="one")
    _write_snapshot(settings, matchday=2, match_ids=(101, 202), directory_name="two")

    report = collect_season_coverage(settings)

    assert report.duplicate_provider_match_ids == (101,)
    assert report.capture_is_complete is False
