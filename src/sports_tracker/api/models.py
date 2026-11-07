"""Public API models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(ApiModel):
    limit: int
    offset: int
    total: int


class Competition(ApiModel):
    competition_season_id: int
    provider: str
    name: str
    shortcut: str
    season: str
    provider_league_id: int


class MatchdaySummary(ApiModel):
    competition_season_id: int
    matchday_number: int
    match_count: int
    finished_count: int
    unfinished_count: int
    first_kickoff_utc: datetime | None = None
    last_kickoff_utc: datetime | None = None


class MatchSummary(ApiModel):
    match_id: int
    provider_match_id: int
    matchday_number: int | None = None
    stage_name: str | None = None
    kickoff_utc: datetime | None = None
    is_finished: bool
    home_team: str
    away_team: str
    home_score: int | None = None
    away_score: int | None = None
    last_source_update_utc: datetime | None = None


class MatchPage(Page):
    items: list[MatchSummary]


class DashboardSummary(ApiModel):
    """Aggregate facts for one loaded competition season or all loaded seasons."""

    total_fixtures: int
    finished_fixtures: int
    upcoming_fixtures: int
    goals_recorded: int
    # This remains the field-level event count for API compatibility. It is not a
    # count of distinct fixtures with at least one recorded transition.
    detected_changes: int
    changed_fixtures: int
    latest_successful_sync_at_utc: datetime | None = None
    latest_successful_snapshot_id: int | None = None
    latest_successful_import_run_id: int | None = None


class InsightMatch(ApiModel):
    """A completed fixture used by the read-only insights views."""

    match_id: int
    provider_match_id: int
    matchday_number: int | None = None
    kickoff_utc: datetime | None = None
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    total_goals: int
    observed_goal_events: int


class TeamLeader(ApiModel):
    team_id: int
    team_name: str
    value: int
    matches_played: int


class InsightSummary(ApiModel):
    competition_season_id: int | None = None
    fixtures_total: int
    fixtures_finished: int
    fixtures_unfinished: int
    completed_matches_with_valid_final_score: int
    full_time_goals: int
    average_full_time_goals_per_completed_match: float | None = None
    home_wins: int
    draws: int
    away_wins: int
    observed_goal_events: int
    highest_scoring_matches: list[InsightMatch] = Field(default_factory=list)
    most_goals_teams: list[TeamLeader] = Field(default_factory=list)
    fewest_conceded_teams: list[TeamLeader] = Field(default_factory=list)
    latest_successful_sync_at_utc: datetime | None = None


class TeamSplit(ApiModel):
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    clean_sheets: int


class TeamInsight(ApiModel):
    team_id: int
    provider_team_id: int
    team_name: str
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    home: TeamSplit
    away: TeamSplit
    recent_form: list[str] = Field(default_factory=list)
    observed_goal_events: int
    clean_sheets: int


class TeamRecentMatch(ApiModel):
    match_id: int
    provider_match_id: int
    matchday_number: int | None = None
    kickoff_utc: datetime | None = None
    home_team: str
    away_team: str
    team_score: int
    opponent_score: int
    outcome: str


class TeamInsightDetail(TeamInsight):
    recent_matches: list[TeamRecentMatch] = Field(default_factory=list)


class MatchdayInsight(ApiModel):
    matchday_number: int | None = None
    fixture_count: int
    finished_count: int
    unfinished_count: int
    completed_matches_with_valid_final_score: int
    full_time_goals: int
    average_full_time_goals: float | None = None
    home_wins: int
    draws: int
    away_wins: int
    observed_goal_events: int


class Result(ApiModel):
    result_type: str
    result_name: str | None = None
    home_score: int | None = None
    away_score: int | None = None


class Goal(ApiModel):
    provider_goal_id: int | None = None
    score_home: int | None = None
    score_away: int | None = None
    minute: int | None = None
    scorer_name: str | None = None
    is_penalty: bool | None = None
    is_own_goal: bool | None = None
    is_overtime: bool | None = None


class MatchDetail(MatchSummary):
    venue: str | None = None
    results: list[Result] = Field(default_factory=list)
    goals: list[Goal] = Field(default_factory=list)


class MatchChange(ApiModel):
    match_change_id: int
    field_name: str
    change_kind: str
    old_value: str | None = None
    new_value: str | None = None
    observed_at_utc: datetime
    source_last_update_utc: datetime | None = None
    import_run_id: int
    source_snapshot_id: int


class MatchChangeOverview(MatchChange):
    """A field-level change with enough fixture and snapshot context for the dashboard."""

    match_id: int
    provider_match_id: int
    matchday_number: int | None = None
    home_team: str
    away_team: str
    snapshot_sha256: str | None = None
    snapshot_retrieved_at_utc: datetime | None = None


class MatchChangePage(Page):
    items: list[MatchChangeOverview]


class ImportRun(ApiModel):
    import_run_id: int
    status: str
    started_at_utc: datetime
    completed_at_utc: datetime | None = None
    snapshot_sha256: str | None = None
    matchday_number: int | None = None
    is_replay: bool = False
    matches_seen: int | None = None
    matches_inserted: int | None = None
    matches_updated: int | None = None
    matches_unchanged: int | None = None
    matches_rejected: int | None = None
    results_seen: int | None = None
    validation_issue_count: int | None = None
    failure_phase: str | None = None
    error_message: str | None = None


class ValidationIssue(ApiModel):
    validation_issue_id: int
    severity: str
    issue_code: str
    message: str
    provider_match_id: int | None = None
    created_at_utc: datetime
    import_run_id: int | None = None
    source_snapshot_id: int | None = None


class Note(ApiModel):
    note_id: int
    match_id: int
    note_text: str
    created_by: str | None = None
    is_archived: bool
    created_at_utc: datetime
    updated_at_utc: datetime


class NoteCreate(ApiModel):
    note_text: str = Field(min_length=1, max_length=4000)
    created_by: str = Field(default="local-user", min_length=1, max_length=200)

    @field_validator("note_text", "created_by")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must contain non-whitespace text")
        return value


class NoteUpdate(ApiModel):
    note_text: str = Field(min_length=1, max_length=4000)

    @field_validator("note_text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must contain non-whitespace text")
        return value


class Health(ApiModel):
    status: str
    database: str


class ServiceStatus(ApiModel):
    status: str
    local_only: bool
    note_writes_enabled: bool


class SyncCheckpoint(ApiModel):
    sync_checkpoint_id: int
    provider: str
    scope_key: str
    matchday_number: int | None = None
    last_source_update_utc: datetime | None = None
    last_processed_at_utc: datetime | None = None
    last_successful_snapshot_id: int | None = None
    last_successful_import_run_id: int | None = None
