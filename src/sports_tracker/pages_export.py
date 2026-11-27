"""Build the public GitHub Pages artifact from a reconciled PostgreSQL snapshot."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from contextlib import closing, nullcontext
from datetime import UTC, datetime
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from pydantic import TypeAdapter

from .analytics import (
    build_insights_summary,
    build_matchday_insights,
    build_team_detail,
    build_team_insights,
)
from .api.models import (
    Competition,
    DashboardSummary,
    InsightSummary,
    MatchChange,
    MatchChangeOverview,
    MatchdayInsight,
    MatchdaySummary,
    MatchDetail,
    MatchSummary,
    TeamInsight,
    TeamInsightDetail,
)
from .api.postgres_repository import PostgreSQLRepository
from .config import OpenLigaDBSettings, load_object_storage_settings
from .ingestion import ParsedSnapshot, load_snapshot
from .postgres_snapshot_store import POSTGRES_ARCHIVE_KEYS, PostgreSQLSnapshotStore
from .runtime import ConnectionFactory
from .storage import NeonS3SnapshotStore, SnapshotStore, build_snapshot_object_key

WEB_DIRECTORY = Path(__file__).with_name("web")
EXPORT_PAGE_SIZE = 200


class PagesExportError(RuntimeError):
    """A checked publication invariant failed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PagesExportError(message)


def load_pages_snapshot(directory: Path, source: OpenLigaDBSettings) -> ParsedSnapshot:
    """Keep strict validation, with one exact, previously reviewed source exception."""
    parsed = load_snapshot(directory, source)
    reviewed_variants = {"resultID 129519: 2-0", "resultID 129520: 0-0"}
    if (source.shortcut, source.season, source.expected_league_id, parsed.metadata.matchday) == (
        "ucl",
        2026,
        4946,
        2,
    ) and any(issue.code == "duplicate-result-type" for issue in parsed.errors):
        recovered = load_snapshot(directory, source, allow_conflicting_nonfinal_results=True)
        quarantines = [
            issue
            for issue in recovered.issues
            if issue.code == "conflicting-nonfinal-result-quarantined"
        ]
        if (
            len(quarantines) == 1
            and quarantines[0].source_record_id == "87412"
            and set((quarantines[0].source_value or "").split("; ")) == reviewed_variants
            and len((quarantines[0].source_value or "").split("; ")) == len(reviewed_variants)
        ):
            parsed = recovered
    if not parsed.errors:
        _require(
            len(parsed.matches) == source.expected_fixtures_per_matchday,
            f"Matchday {parsed.metadata.matchday} has unexpected fixture coverage.",
        )
    return parsed


def _complete_pages(fetch) -> list[dict]:
    rows, total = fetch(limit=EXPORT_PAGE_SIZE, offset=0)
    for offset in range(EXPORT_PAGE_SIZE, total, EXPORT_PAGE_SIZE):
        batch, batch_total = fetch(limit=EXPORT_PAGE_SIZE, offset=offset)
        _require(batch_total == total, "A SQL page count changed during export.")
        rows.extend(batch)
    _require(len(rows) == total, "SQL page rows do not match the reported total.")
    return rows


def _scope(repository: PostgreSQLRepository, season_id: int) -> dict:
    summary = DashboardSummary.model_validate(repository.dashboard_summary(season_id))
    matchdays = TypeAdapter(list[MatchdaySummary]).validate_python(repository.matchdays(season_id))
    matches = TypeAdapter(list[MatchSummary]).validate_python(
        _complete_pages(
            lambda **page: repository.matches(
                competition_season_id=season_id, matchday=None, finished=None, search=None, **page
            )
        )
    )
    changes = TypeAdapter(list[MatchChangeOverview]).validate_python(
        _complete_pages(
            lambda **page: repository.match_changes(competition_season_id=season_id, **page)
        )
    )
    rows = repository.insight_rows(season_id)
    insights = InsightSummary.model_validate(
        build_insights_summary(
            rows,
            competition_season_id=season_id,
            latest_successful_sync_at_utc=summary.latest_successful_sync_at_utc,
        )
    )
    teams = TypeAdapter(list[TeamInsight]).validate_python(build_team_insights(rows))
    insight_matchdays = TypeAdapter(list[MatchdayInsight]).validate_python(
        build_matchday_insights(rows)
    )

    match_ids = {match.match_id for match in matches}
    changed_ids = {change.match_id for change in changes}
    finished = sum(match.is_finished for match in matches)
    valid_scores = [
        match
        for match in matches
        if match.is_finished and match.home_score is not None and match.away_score is not None
    ]
    full_time_goals = sum(match.home_score + match.away_score for match in valid_scores)
    _require(
        len(match_ids) == len(matches) == summary.total_fixtures == insights.fixtures_total
        and finished == summary.finished_fixtures == insights.fixtures_finished
        and len(matches) - finished == summary.upcoming_fixtures == insights.fixtures_unfinished
        and summary.goals_recorded == insights.observed_goal_events
        and len(valid_scores) == insights.completed_matches_with_valid_final_score
        and full_time_goals == insights.full_time_goals
        and sum(day.fixture_count for day in insight_matchdays) == len(matches)
        and changed_ids <= match_ids
        and len(changed_ids) == summary.changed_fixtures
        and len({row.match_change_id for row in changes})
        == len(changes)
        == summary.detected_changes,
        "Dashboard SQL counts, fixture scores, analytics or change history do not reconcile.",
    )
    _require(
        Counter({day.matchday_number: day.match_count for day in matchdays})
        == Counter(match.matchday_number for match in matches if match.matchday_number is not None)
        if season_id is not None
        else True,
        "Matchday totals do not reconcile.",
    )
    return {
        "summary": summary.model_dump(mode="json"),
        "matchdays": [day.model_dump(mode="json") for day in matchdays],
        "matches": [match.model_dump(mode="json") for match in matches],
        "changes": [change.model_dump(mode="json") for change in changes],
        "insights": {
            "summary": insights.model_dump(mode="json"),
            "matchdays": [day.model_dump(mode="json") for day in insight_matchdays],
            "teams": [team.model_dump(mode="json") for team in teams],
            "teamDetails": {
                team.provider_team_id: TeamInsightDetail.model_validate(
                    build_team_detail(rows, team.provider_team_id)
                ).model_dump(mode="json")
                for team in teams
            },
        },
    }


def _reconcile_sync_scope(
    connection, source: OpenLigaDBSettings, season_id: int, scope: dict
) -> None:
    """Verify that the committed checkpoints, private blobs and exported fixture IDs agree."""
    if source.raw_snapshot_storage == "postgresql":
        key_settings = POSTGRES_ARCHIVE_KEYS
        store: SnapshotStore = PostgreSQLSnapshotStore(connection)
    elif source.raw_snapshot_storage == "object":
        key_settings = load_object_storage_settings()
        store = NeonS3SnapshotStore(key_settings)
    else:
        raise PagesExportError("Pages export requires durable snapshot storage.")
    checkpoints = connection.execute(
        """
        SELECT cp.matchday_number, ss.local_directory, ss.sha256, ss.byte_count,
               ss.source_url, ss.retrieved_at_utc, runs.matches_seen
        FROM public.sync_checkpoints AS cp
        JOIN public.import_runs AS runs
          ON runs.import_run_id = cp.last_successful_import_run_id
         AND runs.source_snapshot_id = cp.last_successful_snapshot_id
         AND runs.competition_season_id = cp.competition_season_id
         AND runs.matchday_number = cp.matchday_number
        JOIN public.source_snapshots AS ss
          ON ss.source_snapshot_id = cp.last_successful_snapshot_id
         AND ss.matchday_number = cp.matchday_number
        WHERE cp.provider = 'OpenLigaDB' AND cp.competition_season_id = %s
          AND cp.last_processed_at_utc IS NOT NULL
          AND runs.status = 'Succeeded' AND runs.matches_rejected = 0
          AND ss.provider = cp.provider AND ss.provider_shortcut = %s
          AND ss.season_start_year = %s AND ss.source_league_id = %s
        """,
        (season_id, source.shortcut, source.season, source.expected_league_id),
    ).fetchall()
    expected_matchdays = set(source.expected_league_phase_matchdays)
    current_checkpoints = [
        row for row in checkpoints if row["matchday_number"] in expected_matchdays
    ]
    _require(
        {row["matchday_number"] for row in current_checkpoints} == expected_matchdays
        and len(current_checkpoints) == len(expected_matchdays),
        "Expected matchdays do not have one successful checkpoint each.",
    )
    for row in current_checkpoints:
        day = row["matchday_number"]
        timestamp = row["retrieved_at_utc"].astimezone(UTC)
        sha256 = row["sha256"]
        key = build_snapshot_object_key(
            key_settings,
            shortcut=source.shortcut,
            season=source.season,
            matchday=day,
            retrieved_at_utc=timestamp.isoformat(),
            sha256=sha256,
        )
        _require(key == row["local_directory"], f"Matchday {day} has no verified archive locator.")
        snapshot = store.get(key)
        metadata = snapshot.metadata
        _require(
            hashlib.sha256(snapshot.body).hexdigest() == sha256
            and len(snapshot.body) == row["byte_count"]
            and metadata.get("url") == row["source_url"]
            and metadata.get("provider") == "OpenLigaDB"
            and metadata.get("shortcut") == source.shortcut
            and metadata.get("season") == source.season
            and metadata.get("matchday") == day
            and datetime.fromisoformat(str(metadata.get("retrieved_at_utc"))) == timestamp,
            f"Matchday {day} snapshot provenance does not match SQL.",
        )
        records = json.loads(snapshot.body)
        fixture_ids = {
            match["provider_match_id"]
            for match in scope["matches"]
            if match["matchday_number"] == day
        }
        _require(
            len(records)
            == row["matches_seen"]
            == len(fixture_ids)
            == source.expected_fixtures_per_matchday
            and {record["matchID"] for record in records} == fixture_ids,
            f"Matchday {day} snapshot fixture IDs or expected coverage do not match SQL.",
        )


def export_pages(
    output: Path,
    connection_factory: ConnectionFactory,
    source: OpenLigaDBSettings,
    synchronized_at: datetime,
) -> None:
    """Validate a complete, read-consistent export before creating a deployable directory."""
    with closing(connection_factory()) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        repository = PostgreSQLRepository(
            connection_factory, read_connection=lambda: nullcontext(connection)
        )
        competitions = TypeAdapter(list[Competition]).validate_python(repository.competitions())
        seasons = connection.execute(
            """
            SELECT cs.competition_season_id
            FROM public.competition_seasons AS cs
            JOIN public.competitions AS c ON c.competition_id = cs.competition_id
            WHERE c.provider = 'OpenLigaDB' AND c.provider_shortcut = %s
              AND cs.season_start_year = %s AND cs.source_league_id = %s
            """,
            (source.shortcut, source.season, source.expected_league_id),
        ).fetchall()
        _require(len(seasons) == 1, "The synchronized competition season is missing or ambiguous.")
        season_id = seasons[0]["competition_season_id"]
        competition = next(item for item in competitions if item.competition_season_id == season_id)
        scope = _scope(repository, season_id)
        _reconcile_sync_scope(connection, source, season_id, scope)
        match_details = {}
        history = {}
        changes_by_match = {}
        for row in scope["changes"]:
            changes_by_match.setdefault(row["match_id"], []).append(MatchChange.model_validate(row))
        for match in scope["matches"]:
            match_id = match["match_id"]
            detail = MatchDetail.model_validate(repository.match(match_id))
            _require(
                detail.model_dump(mode="json", include=set(MatchSummary.model_fields)) == match,
                "Match detail and fixture list disagree.",
            )
            changes = TypeAdapter(list[MatchChange]).validate_python(repository.changes(match_id))
            _require(
                changes == changes_by_match.get(match_id, []),
                "Match change history does not reconcile.",
            )
            match_details[match_id] = detail.model_dump(mode="json")
            history[match_id] = [change.model_dump(mode="json") for change in changes]
        _require(
            sum(len(detail["goals"]) for detail in match_details.values())
            == scope["summary"]["goals_recorded"],
            "Match goal details do not reconcile with the SQL aggregate.",
        )

    payload = {
        "schemaVersion": 1,
        "synchronizedAt": synchronized_at.astimezone(UTC).isoformat(),
        "competitions": [competition.model_dump(mode="json")],
        "scope": scope,
        "matchDetails": match_details,
        "matchHistory": history,
    }
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    payload["revision"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    content = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"

    output.parent.mkdir(parents=True, exist_ok=True)
    _require(not output.exists(), "The Pages output directory already exists.")
    with TemporaryDirectory(dir=output.parent, prefix=".pages-") as temporary:
        staging = Path(temporary) / "public"
        (staging / "assets").mkdir(parents=True)
        (staging / "data").mkdir()
        (staging / ".nojekyll").touch()
        html = (WEB_DIRECTORY / "index.html").read_text(encoding="utf-8")
        html = html.replace(
            "<head>", '<head>\n    <meta name="dashboard-data" content="./data/dashboard.json">', 1
        )
        html = re.sub(r'(?<=["\x27])/assets/', "./assets/", html)
        (staging / "index.html").write_text(html, encoding="utf-8")
        for name in ("app.js", "styles.css"):
            copyfile(WEB_DIRECTORY / name, staging / "assets" / name)
        (staging / "data" / "dashboard.json").write_text(content, encoding="utf-8")
        staging.rename(output)
