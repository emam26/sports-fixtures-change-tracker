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
