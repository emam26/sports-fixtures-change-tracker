"""Read-only football analytics over validated current fixture records.

The service deliberately works from one denormalized row per fixture supplied by
the repository.  The repository pre-aggregates goal-event counts before joining
them, so a fixture with several goals cannot multiply a result row.  Only an
``After90Minutes`` result with two non-null scores on a provider-finished match is
considered a valid final score.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol


class AnalyticsDataSource(Protocol):
    def insight_rows(self, competition_season_id: int | None) -> list[dict[str, Any]]: ...

    def insight_latest_successful_sync(
        self,
        competition_season_id: int | None,
    ) -> datetime | None: ...


def _int_value(value: object, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_finished(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _kickoff_timestamp(value: object) -> float | None:
    if not isinstance(value, datetime):
        return None
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.timestamp()


def _fixture_sort_key(row: Mapping[str, Any]) -> tuple[int, float, int]:
    timestamp = _kickoff_timestamp(row.get("kickoff_utc"))
    return (
        1 if timestamp is None else 0,
        timestamp if timestamp is not None else 0.0,
        _int_value(row.get("match_id")),
    )


def _recent_sort_key(row: Mapping[str, Any]) -> tuple[int, float, int]:
    timestamp = _kickoff_timestamp(row.get("kickoff_utc"))
    return (
        0 if timestamp is None else 1,
        timestamp if timestamp is not None else 0.0,
        _int_value(row.get("match_id")),
    )


def _valid_final(row: Mapping[str, Any]) -> bool:
    return (
        _is_finished(row.get("is_finished"))
        and _optional_int(row.get("home_score")) is not None
        and _optional_int(row.get("away_score")) is not None
    )


def _completed_rows(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [row for row in rows if _valid_final(row)]


def _result_kind(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if away_score > home_score:
        return "away"
    return "draw"


def _insight_match(row: Mapping[str, Any]) -> dict[str, Any]:
    home_score = _optional_int(row.get("home_score"))
    away_score = _optional_int(row.get("away_score"))
    if home_score is None or away_score is None:
        raise ValueError("An insight match requires a valid final score")
    return {
        "match_id": _int_value(row.get("match_id")),
        "provider_match_id": _int_value(row.get("provider_match_id")),
        "matchday_number": _optional_int(row.get("matchday_number")),
        "kickoff_utc": row.get("kickoff_utc"),
        "home_team": str(row.get("home_team") or "Unknown home team"),
        "away_team": str(row.get("away_team") or "Unknown away team"),
        "home_score": home_score,
        "away_score": away_score,
        "total_goals": home_score + away_score,
        "observed_goal_events": _int_value(row.get("observed_goal_events")),
    }


def build_insights_summary(
    rows: Sequence[Mapping[str, Any]],
    *,
    competition_season_id: int | None,
    latest_successful_sync_at_utc: datetime | None,
) -> dict[str, Any]:
    completed = _completed_rows(rows)
    home_wins = sum(
        _result_kind(_int_value(row.get("home_score")), _int_value(row.get("away_score"))) == "home"
        for row in completed
    )
    draws = sum(
        _result_kind(_int_value(row.get("home_score")), _int_value(row.get("away_score"))) == "draw"
        for row in completed
    )
    away_wins = len(completed) - home_wins - draws
    full_time_goals = sum(
        _int_value(row.get("home_score")) + _int_value(row.get("away_score")) for row in completed
    )
    highest = sorted(
        (_insight_match(row) for row in completed),
        key=lambda item: (
            -item["total_goals"],
            _kickoff_timestamp(item["kickoff_utc"]) is None,
            _kickoff_timestamp(item["kickoff_utc"])
            if _kickoff_timestamp(item["kickoff_utc"]) is not None
            else 0.0,
            item["match_id"],
        ),
    )[:5]
    team_insights = build_team_insights(rows)
    most_goals = sorted(
        (item for item in team_insights if item["played"] > 0),
        key=lambda item: (-item["goals_for"], item["team_name"].casefold(), item["team_id"]),
    )[:3]
    fewest_conceded = sorted(
        (item for item in team_insights if item["played"] > 0),
        key=lambda item: (
            item["goals_against"],
            -item["played"],
            item["team_name"].casefold(),
            item["team_id"],
        ),
    )[:3]

    def leader(item: Mapping[str, Any], value_key: str) -> dict[str, Any]:
        return {
            "team_id": item["team_id"],
            "team_name": item["team_name"],
            "value": item[value_key],
            "matches_played": item["played"],
        }

    return {
        "competition_season_id": competition_season_id,
        "fixtures_total": len(rows),
        "fixtures_finished": sum(_is_finished(row.get("is_finished")) for row in rows),
        "fixtures_unfinished": sum(not _is_finished(row.get("is_finished")) for row in rows),
        "completed_matches_with_valid_final_score": len(completed),
        "full_time_goals": full_time_goals,
        "average_full_time_goals_per_completed_match": (
            full_time_goals / len(completed) if completed else None
        ),
        "home_wins": home_wins,
        "draws": draws,
        "away_wins": away_wins,
        "observed_goal_events": sum(
            _int_value(row.get("observed_goal_events")) for row in completed
        ),
        "highest_scoring_matches": highest,
        "most_goals_teams": [leader(item, "goals_for") for item in most_goals],
        "fewest_conceded_teams": [leader(item, "goals_against") for item in fewest_conceded],
        "latest_successful_sync_at_utc": latest_successful_sync_at_utc,
    }


def _empty_split() -> dict[str, int]:
    return {
        "played": 0,
        "won": 0,
        "drawn": 0,
        "lost": 0,
        "goals_for": 0,
        "goals_against": 0,
        "goal_difference": 0,
        "points": 0,
        "clean_sheets": 0,
    }


def _update_split(split: dict[str, int], goals_for: int, goals_against: int) -> str:
    split["played"] += 1
    split["goals_for"] += goals_for
    split["goals_against"] += goals_against
    split["goal_difference"] = split["goals_for"] - split["goals_against"]
    if goals_against == 0:
        split["clean_sheets"] += 1
    if goals_for > goals_against:
        split["won"] += 1
        split["points"] += 3
        return "W"
    if goals_for == goals_against:
        split["drawn"] += 1
        split["points"] += 1
        return "D"
    split["lost"] += 1
    return "L"


def _team_accumulator(team_id: int, name: str) -> dict[str, Any]:
    return {
        "team_id": team_id,
        "provider_team_id": team_id,
        "team_name": name,
        "home": _empty_split(),
        "away": _empty_split(),
        "recent": [],
        "observed_goal_events": 0,
    }


def _team_rows(rows: Sequence[Mapping[str, Any]]) -> dict[int, dict[str, Any]]:
    teams: dict[int, dict[str, Any]] = {}
    for row in rows:
        for id_key, name_key in (
            ("home_team_provider_id", "home_team"),
            ("away_team_provider_id", "away_team"),
        ):
            team_id = _optional_int(row.get(id_key))
            if team_id is not None and team_id not in teams:
                teams[team_id] = _team_accumulator(
                    team_id,
                    str(row.get(name_key) or f"Team {team_id}"),
                )
    return teams


def _team_insight(accumulator: Mapping[str, Any]) -> dict[str, Any]:
    home = accumulator["home"]
    away = accumulator["away"]
    combined = {
        "played": home["played"] + away["played"],
        "won": home["won"] + away["won"],
        "drawn": home["drawn"] + away["drawn"],
        "lost": home["lost"] + away["lost"],
        "goals_for": home["goals_for"] + away["goals_for"],
        "goals_against": home["goals_against"] + away["goals_against"],
        "goal_difference": home["goal_difference"] + away["goal_difference"],
        "points": home["points"] + away["points"],
        "clean_sheets": home["clean_sheets"] + away["clean_sheets"],
    }
    recent = sorted(
        accumulator["recent"],
        key=lambda item: _recent_sort_key(item["row"]),
        reverse=True,
    )
    return {
        **combined,
        "team_id": accumulator["team_id"],
        "provider_team_id": accumulator["provider_team_id"],
        "team_name": accumulator["team_name"],
        "home": home,
        "away": away,
        "recent_form": [item["outcome"] for item in recent[:5]],
        "observed_goal_events": accumulator["observed_goal_events"],
        "clean_sheets": combined["clean_sheets"],
    }


def build_team_insights(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    teams = _team_rows(rows)
    for row in _completed_rows(rows):
        home_id = _optional_int(row.get("home_team_provider_id"))
        away_id = _optional_int(row.get("away_team_provider_id"))
        home_score = _int_value(row.get("home_score"))
        away_score = _int_value(row.get("away_score"))
        if home_id is None or away_id is None or home_id not in teams or away_id not in teams:
            continue
        home_outcome = _update_split(teams[home_id]["home"], home_score, away_score)
        away_outcome = _update_split(teams[away_id]["away"], away_score, home_score)
        goal_events = _int_value(row.get("observed_goal_events"))
        teams[home_id]["observed_goal_events"] += goal_events
        teams[away_id]["observed_goal_events"] += goal_events
        teams[home_id]["recent"].append(
            {
                "row": row,
                "outcome": home_outcome,
                "team_score": home_score,
                "opponent_score": away_score,
            }
        )
        teams[away_id]["recent"].append(
            {
                "row": row,
                "outcome": away_outcome,
                "team_score": away_score,
                "opponent_score": home_score,
            }
        )
    return sorted(
        (_team_insight(accumulator) for accumulator in teams.values()),
        key=lambda item: (
            -item["points"],
            -item["goal_difference"],
            -item["goals_for"],
            item["team_name"].casefold(),
            item["provider_team_id"],
        ),
    )


def build_team_detail(
    rows: Sequence[Mapping[str, Any]],
    team_id: int,
) -> dict[str, Any] | None:
    teams = build_team_insights(rows)
    team = next((item for item in teams if item["provider_team_id"] == team_id), None)
    if team is None:
        return None
    recent: list[dict[str, Any]] = []
    for row in sorted(_completed_rows(rows), key=_recent_sort_key, reverse=True):
        home_id = _optional_int(row.get("home_team_provider_id"))
        away_id = _optional_int(row.get("away_team_provider_id"))
        if team_id not in {home_id, away_id}:
            continue
        home_score = _int_value(row.get("home_score"))
        away_score = _int_value(row.get("away_score"))
        is_home = team_id == home_id
        team_score = home_score if is_home else away_score
        opponent_score = away_score if is_home else home_score
        recent.append(
            {
                "match_id": _int_value(row.get("match_id")),
                "provider_match_id": _int_value(row.get("provider_match_id")),
                "matchday_number": _optional_int(row.get("matchday_number")),
                "kickoff_utc": row.get("kickoff_utc"),
                "home_team": str(row.get("home_team") or "Unknown home team"),
                "away_team": str(row.get("away_team") or "Unknown away team"),
                "team_score": team_score,
                "opponent_score": opponent_score,
                "outcome": (
                    "W"
                    if team_score > opponent_score
                    else "D"
                    if team_score == opponent_score
                    else "L"
                ),
            }
        )
    team["recent_matches"] = recent[:5]
    return team


def build_matchday_insights(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int | None, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_optional_int(row.get("matchday_number"))].append(row)
    result: list[dict[str, Any]] = []
    for matchday, matchday_rows in grouped.items():
        completed = _completed_rows(matchday_rows)
        home_wins = sum(
            _result_kind(_int_value(row.get("home_score")), _int_value(row.get("away_score")))
            == "home"
            for row in completed
        )
        draws = sum(
            _result_kind(_int_value(row.get("home_score")), _int_value(row.get("away_score")))
            == "draw"
            for row in completed
        )
        goals = sum(
            _int_value(row.get("home_score")) + _int_value(row.get("away_score"))
            for row in completed
        )
        result.append(
            {
                "matchday_number": matchday,
                "fixture_count": len(matchday_rows),
                "finished_count": sum(
                    _is_finished(row.get("is_finished")) for row in matchday_rows
                ),
                "unfinished_count": sum(
                    not _is_finished(row.get("is_finished")) for row in matchday_rows
                ),
                "completed_matches_with_valid_final_score": len(completed),
                "full_time_goals": goals,
                "average_full_time_goals": goals / len(completed) if completed else None,
                "home_wins": home_wins,
                "draws": draws,
                "away_wins": len(completed) - home_wins - draws,
                "observed_goal_events": sum(
                    _int_value(row.get("observed_goal_events")) for row in completed
                ),
            }
        )
    return sorted(
        result,
        key=lambda item: (item["matchday_number"] is None, item["matchday_number"] or 0),
    )


class AnalyticsService:
    """Calculate read-only insights from one repository fixture-row snapshot."""

    def __init__(self, source: AnalyticsDataSource) -> None:
        self._source = source

    def summary(self, competition_season_id: int | None) -> dict[str, Any]:
        rows = self._source.insight_rows(competition_season_id)
        return build_insights_summary(
            rows,
            competition_season_id=competition_season_id,
            latest_successful_sync_at_utc=self._source.insight_latest_successful_sync(
                competition_season_id
            ),
        )

    def teams(self, competition_season_id: int | None) -> list[dict[str, Any]]:
        return build_team_insights(self._source.insight_rows(competition_season_id))

    def matchdays(self, competition_season_id: int | None) -> list[dict[str, Any]]:
        return build_matchday_insights(self._source.insight_rows(competition_season_id))

    def team(self, competition_season_id: int | None, team_id: int) -> dict[str, Any] | None:
        return build_team_detail(self._source.insight_rows(competition_season_id), team_id)
