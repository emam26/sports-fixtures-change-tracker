from __future__ import annotations

from datetime import UTC, datetime

from sports_tracker.analytics import (
    AnalyticsService,
    build_insights_summary,
    build_matchday_insights,
    build_team_detail,
    build_team_insights,
)

NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)


def _row(
    match_id: int,
    *,
    matchday: int,
    kickoff: datetime | None,
    finished: bool,
    home_id: int,
    away_id: int,
    home: str,
    away: str,
    home_score: int | None,
    away_score: int | None,
    goal_events: int,
) -> dict[str, object]:
    return {
        "match_id": match_id,
        "provider_match_id": match_id + 10000,
        "matchday_number": matchday,
        "kickoff_utc": kickoff,
        "is_finished": finished,
        "home_team_provider_id": home_id,
        "away_team_provider_id": away_id,
        "home_team": home,
        "away_team": away,
        "home_score": home_score,
        "away_score": away_score,
        "observed_goal_events": goal_events,
    }


def _rows() -> list[dict[str, object]]:
    return [
        _row(
            1,
            matchday=1,
            kickoff=datetime(2026, 9, 15, 19, tzinfo=UTC),
            finished=True,
            home_id=10,
            away_id=20,
            home="Alpha",
            away="Beta",
            home_score=2,
            away_score=1,
            goal_events=3,
        ),
        _row(
            2,
            matchday=2,
            kickoff=datetime(2026, 10, 1, 19, tzinfo=UTC),
            finished=True,
            home_id=20,
            away_id=10,
            home="Beta",
            away="Alpha",
            home_score=0,
            away_score=0,
            goal_events=0,
        ),
        _row(
            3,
            matchday=3,
            kickoff=datetime(2026, 11, 1, 19, tzinfo=UTC),
            finished=False,
            home_id=10,
            away_id=20,
            home="Alpha",
            away="Beta",
            home_score=None,
            away_score=None,
            goal_events=0,
        ),
        _row(
            4,
            matchday=3,
            kickoff=None,
            finished=True,
            home_id=10,
            away_id=20,
            home="Alpha",
            away="Beta",
            home_score=None,
            away_score=None,
            goal_events=4,
        ),
    ]


def test_summary_uses_only_valid_after90_completed_scores() -> None:
    summary = build_insights_summary(
        _rows(),
        competition_season_id=7,
        latest_successful_sync_at_utc=NOW,
    )

    assert summary["fixtures_total"] == 4
    assert summary["fixtures_finished"] == 3
    assert summary["fixtures_unfinished"] == 1
    assert summary["completed_matches_with_valid_final_score"] == 2
    assert summary["full_time_goals"] == 3
    assert summary["average_full_time_goals_per_completed_match"] == 1.5
    assert (summary["home_wins"], summary["draws"], summary["away_wins"]) == (1, 1, 0)
    assert summary["observed_goal_events"] == 3
    assert summary["highest_scoring_matches"][0]["provider_match_id"] == 10001
    assert summary["most_goals_teams"][0]["team_name"] == "Alpha"
    assert summary["fewest_conceded_teams"][0]["team_name"] == "Alpha"


def test_team_insights_include_home_away_splits_and_recent_form() -> None:
    teams = build_team_insights(_rows())

    alpha = next(team for team in teams if team["provider_team_id"] == 10)
    assert alpha["played"] == 2
    assert alpha["won"] == 1
    assert alpha["drawn"] == 1
    assert alpha["points"] == 4
    assert alpha["goals_for"] == 2
    assert alpha["goals_against"] == 1
    assert alpha["home"]["played"] == 1
    assert alpha["away"]["drawn"] == 1
    assert alpha["recent_form"] == ["D", "W"]
    assert alpha["observed_goal_events"] == 3
    assert alpha["clean_sheets"] == 1


def test_matchday_insights_keep_unfinished_counts_and_null_scores_out_of_averages() -> None:
    matchdays = build_matchday_insights(_rows())

    assert matchdays[0]["matchday_number"] == 1
    assert matchdays[0]["average_full_time_goals"] == 3
    third = next(item for item in matchdays if item["matchday_number"] == 3)
    assert third["fixture_count"] == 2
    assert third["finished_count"] == 1
    assert third["unfinished_count"] == 1
    assert third["completed_matches_with_valid_final_score"] == 0
    assert third["average_full_time_goals"] is None


def test_team_detail_has_recent_results_without_fabricating_missing_scores() -> None:
    detail = build_team_detail(_rows(), 10)

    assert detail is not None
    assert [item["outcome"] for item in detail["recent_matches"]] == ["D", "W"]
    assert build_team_detail(_rows(), 999) is None


class _Source:
    def insight_rows(self, competition_season_id: int | None) -> list[dict[str, object]]:
        assert competition_season_id == 7
        return _rows()

    def insight_latest_successful_sync(self, competition_season_id: int | None) -> datetime:
        assert competition_season_id == 7
        return NOW


def test_analytics_service_uses_repository_snapshot_and_sync_timestamp() -> None:
    summary = AnalyticsService(_Source()).summary(7)

    assert summary["competition_season_id"] == 7
    assert summary["latest_successful_sync_at_utc"] == NOW
