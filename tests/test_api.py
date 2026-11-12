from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from sports_tracker.api.app import _is_public_readonly_request, create_app
from sports_tracker.config import ApplicationSettings


def test_application_lifespan_closes_repository() -> None:
    closed = []

    class ClosableRepository(FakeRepository):
        def close(self) -> None:
            closed.append(True)

    repository = ClosableRepository()

    with _test_client(create_app(repository=repository, settings=_settings())):
        pass

    assert closed == [True]


class FakeRepository:
    def __init__(self) -> None:
        self.note = {
            "note_id": 1,
            "match_id": 10,
            "note_text": "Review lineup",
            "created_by": "tester",
            "is_archived": False,
            "created_at_utc": datetime(2026, 11, 3, tzinfo=UTC),
            "updated_at_utc": datetime(2026, 11, 3, tzinfo=UTC),
        }
        self.last_filters: dict[str, Any] = {}
        self.last_summary_competition_id: int | None = None
        self.last_change_filters: dict[str, int | None] = {}

    def health(self) -> None:
        return None

    def competitions(self) -> list[dict[str, Any]]:
        return [
            {
                "competition_season_id": 1,
                "provider": "OpenLigaDB",
                "name": "UEFA Champions League",
                "shortcut": "ucl",
                "season": "2026",
                "provider_league_id": 4946,
            }
        ]

    def matchdays(self, competition_season_id: int | None) -> list[dict[str, Any]]:
        assert competition_season_id in {None, 1}
        return [
            {
                "competition_season_id": 1,
                "matchday_number": 3,
                "match_count": 18,
                "finished_count": 18,
                "unfinished_count": 0,
                "first_kickoff_utc": datetime(2026, 10, 20, 16, 45, tzinfo=UTC),
                "last_kickoff_utc": datetime(2026, 10, 21, 19, 0, tzinfo=UTC),
            }
        ]

    def matches(self, **filters: Any) -> tuple[list[dict[str, Any]], int]:
        self.last_filters = filters
        if filters["finished"] is False:
            return [self._upcoming_match(), self._upcoming_match(missing_kickoff=True)], 2
        return [self._match()], 1

    def dashboard_summary(self, competition_season_id: int | None) -> dict[str, Any]:
        self.last_summary_competition_id = competition_season_id
        return {
            "total_fixtures": 18,
            "finished_fixtures": 18,
            "upcoming_fixtures": 0,
            "goals_recorded": 74,
            "detected_changes": 1,
            "changed_fixtures": 1,
            "latest_successful_sync_at_utc": datetime(2026, 11, 3, tzinfo=UTC),
            "latest_successful_snapshot_id": 8,
            "latest_successful_import_run_id": 3,
        }

    def freshness(self, competition_season_id: int | None) -> dict[str, Any]:
        assert competition_season_id in {None, 1}
        return {
            "revision": "revision-3",
            "latest_successful_sync_at_utc": datetime(2026, 11, 3, tzinfo=UTC),
        }

    def insight_rows(self, competition_season_id: int | None) -> list[dict[str, Any]]:
        assert competition_season_id in {None, 1}
        return [
            {
                "match_id": 10,
                "provider_match_id": 123,
                "matchday_number": 3,
                "kickoff_utc": datetime(2026, 10, 20, 19, tzinfo=UTC),
                "is_finished": True,
                "home_team_provider_id": 101,
                "away_team_provider_id": 102,
                "home_team": "Alpha FC",
                "away_team": "Beta FC",
                "home_score": 2,
                "away_score": 1,
                "observed_goal_events": 3,
            }
        ]

    def insight_latest_successful_sync(
        self,
        competition_season_id: int | None,
    ) -> datetime:
        assert competition_season_id in {None, 1}
        return datetime(2026, 11, 3, tzinfo=UTC)

    def _match(self) -> dict[str, Any]:
        return {
            "match_id": 10,
            "provider_match_id": 123,
            "matchday_number": 3,
            "stage_name": "League phase",
            "kickoff_utc": datetime(2026, 10, 20, 19, tzinfo=UTC),
            "is_finished": True,
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "home_score": 2,
            "away_score": 1,
            "last_source_update_utc": datetime(2026, 10, 20, 22, tzinfo=UTC),
        }

    def _upcoming_match(self, *, missing_kickoff: bool = False) -> dict[str, Any]:
        kickoff_utc = None if missing_kickoff else datetime(2026, 11, 10, tzinfo=UTC)
        return {
            "match_id": 12 if missing_kickoff else 11,
            "provider_match_id": 125 if missing_kickoff else 124,
            "matchday_number": 5,
            "stage_name": "League phase",
            "kickoff_utc": kickoff_utc,
            "is_finished": False,
            "home_team": "Future Home FC",
            "away_team": "Future Away FC",
            "home_score": None,
            "away_score": None,
            "last_source_update_utc": None,
        }

    def match(self, match_id: int) -> dict[str, Any] | None:
        if match_id != 10:
            return None
        return {
            **self._match(),
            "venue": "Example Ground",
            "results": [
                {
                    "result_type": "After90Minutes",
                    "result_name": "Endergebnis",
                    "home_score": 2,
                    "away_score": 1,
                }
            ],
            "goals": [],
        }

    def changes(self, match_id: int) -> list[dict[str, Any]]:
        if match_id != 10:
            return []
        observed_at = datetime(2026, 11, 3, tzinfo=UTC)
        return [
            {
                "match_change_id": 6,
                "field_name": "source_match_is_finished",
                "change_kind": "Updated",
                "old_value": "false",
                "new_value": "true",
                "observed_at_utc": observed_at,
                "source_last_update_utc": None,
                "import_run_id": 3,
                "source_snapshot_id": 8,
            },
            {
                "match_change_id": 7,
                "field_name": "result.2002.result_type_kind",
                "change_kind": "Inserted",
                "old_value": None,
                "new_value": "After90Minutes",
                "observed_at_utc": observed_at,
                "source_last_update_utc": None,
                "import_run_id": 3,
                "source_snapshot_id": 8,
            },
            {
                "match_change_id": 8,
                "field_name": "result.2002.points_team1",
                "change_kind": "Inserted",
                "old_value": None,
                "new_value": "2",
                "observed_at_utc": observed_at,
                "source_last_update_utc": None,
                "import_run_id": 3,
                "source_snapshot_id": 8,
            },
            {
                "match_change_id": 9,
                "field_name": "goal.152095.goal_getter_provider_id",
                "change_kind": "Inserted",
                "old_value": None,
                "new_value": "1234",
                "observed_at_utc": observed_at,
                "source_last_update_utc": None,
                "import_run_id": 3,
                "source_snapshot_id": 8,
            },
        ]

    def match_changes(
        self,
        *,
        competition_season_id: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        self.last_change_filters = {
            "competition_season_id": competition_season_id,
            "limit": limit,
            "offset": offset,
        }
        return [
            {
                "match_change_id": 5,
                "match_id": 10,
                "provider_match_id": 123,
                "matchday_number": 3,
                "home_team": "Alpha FC",
                "away_team": "Beta FC",
                "field_name": "source_match_is_finished",
                "change_kind": "updated",
                "old_value": "false",
                "new_value": "true",
                "observed_at_utc": datetime(2026, 11, 3, tzinfo=UTC),
                "source_last_update_utc": datetime(2026, 11, 3, tzinfo=UTC),
                "import_run_id": 3,
                "source_snapshot_id": 8,
                "snapshot_sha256": "a" * 64,
                "snapshot_retrieved_at_utc": datetime(2026, 11, 3, tzinfo=UTC),
            }
        ], 1

    def sync_checkpoints(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        return [
            {
                "sync_checkpoint_id": 1,
                "provider": "OpenLigaDB",
                "scope_key": "OpenLigaDB:ucl:2026:matchday:3",
                "matchday_number": 3,
                "last_source_update_utc": None,
                "last_processed_at_utc": datetime(2026, 11, 3, tzinfo=UTC),
                "last_successful_snapshot_id": 8,
                "last_successful_import_run_id": 3,
            }
        ], 1

    def import_runs(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        return [], 0

    def validation_issues(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        return [], 0

    def notes(self, match_id: int) -> list[dict[str, Any]]:
        if match_id != 10 or self.note["is_archived"]:
            return []
        return [self.note]

    def create_note(self, match_id: int, note_text: str, created_by: str) -> dict[str, Any]:
        self.note = {
            **self.note,
            "match_id": match_id,
            "note_text": note_text,
            "created_by": created_by,
        }
        return self.note

    def update_note(self, note_id: int, note_text: str) -> dict[str, Any] | None:
        if note_id != 1:
            return None
        self.note["note_text"] = note_text
        return self.note

    def archive_note(self, note_id: int) -> bool:
        if note_id != 1:
            return False
        self.note["is_archived"] = True
        return True


def _settings(*, writes: bool = False) -> ApplicationSettings:
    return ApplicationSettings(
        local_only=True,
        allow_note_writes=writes,
        notes_write_token="a-secure-local-token" if writes else None,
    )


def _public_settings() -> ApplicationSettings:
    return ApplicationSettings(
        local_only=False,
        allow_note_writes=False,
        notes_write_token=None,
        deployment_mode="public_readonly",
    )


def _test_client(application: Any, **kwargs: Any) -> TestClient:
    return TestClient(application, client=("127.0.0.1", 8000), **kwargs)


def test_application_factory_accepts_valid_local_settings_injection() -> None:
    settings = _settings()

    application = create_app(FakeRepository(), settings)

    assert application.state.settings is settings
    assert application.state.settings.deployment_mode == "local"
    assert application.state.settings.local_only is True


def test_match_filters_are_validated_and_forwarded() -> None:
    repository = FakeRepository()
    client = _test_client(create_app(repository, _settings()))

    response = client.get("/api/matches?matchday=3&finished=true&search=Alpha&sort=kickoff-desc")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert repository.last_filters["matchday"] == 3
    assert repository.last_filters["finished"] is True
    assert repository.last_filters["search"] == "Alpha"
    assert repository.last_filters["sort"] == "kickoff-desc"


def test_match_sort_rejects_unknown_values() -> None:
    client = _test_client(create_app(FakeRepository(), _settings()))

    response = client.get("/api/matches?sort=database-order")

    assert response.status_code == 422


def test_upcoming_fixture_filter_preserves_nullable_scores_and_missing_kickoff() -> None:
    repository = FakeRepository()
    client = _test_client(create_app(repository, _settings()))

    response = client.get("/api/matches?finished=false&limit=6")

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert all(item["is_finished"] is False for item in response.json()["items"])
    assert all(item["home_score"] is None for item in response.json()["items"])
    assert response.json()["items"][1]["kickoff_utc"] is None
    assert repository.last_filters["finished"] is False
    assert repository.last_filters["sort"] == "explorer"


def test_status_matchdays_and_checkpoints_are_exposed_without_secrets() -> None:
    client = _test_client(create_app(FakeRepository(), _settings(writes=True)))

    status_response = client.get("/api/status")
    matchdays_response = client.get("/api/matchdays?competition_season_id=1")
    checkpoints_response = client.get("/api/sync-checkpoints")
    import_runs_response = client.get("/api/import-runs")
    validation_issues_response = client.get("/api/validation-issues")

    assert status_response.status_code == 200
    assert status_response.json() == {
        "status": "ok",
        "local_only": True,
        "note_writes_enabled": True,
    }
    assert "token" not in status_response.text.lower()
    assert matchdays_response.json()[0]["match_count"] == 18
    assert checkpoints_response.json()[0]["last_successful_import_run_id"] == 3
    assert import_runs_response.status_code == 200
    assert validation_issues_response.status_code == 200
    assert import_runs_response.json() == []
    assert validation_issues_response.json() == []


def test_public_readonly_mode_allows_only_dashboard_get_routes() -> None:
    client = _test_client(create_app(FakeRepository(), _public_settings()))

    allowed_paths = (
        "/",
        "/assets/app.js?cache=public",
        "/assets/styles.css",
        "/api/status",
        "/api/competitions",
        "/api/matchdays",
        "/api/matches",
        "/api/matches/10",
        "/api/matches/10/changes",
        "/api/dashboard-summary",
        "/api/freshness",
        "/api/insights/summary",
        "/api/insights/teams",
        "/api/insights/teams/101",
        "/api/insights/matchdays",
        "/api/match-changes",
    )

    for path in allowed_paths:
        response = client.get(path)
        assert response.status_code == 200, path

    assert client.get("/api/status").json() == {
        "status": "ok",
        "local_only": False,
        "note_writes_enabled": False,
    }


def test_public_readonly_mode_denies_internal_and_unapproved_paths() -> None:
    repository = FakeRepository()
    client = _test_client(create_app(repository, _public_settings()))

    denied_paths = (
        "/health",
        "/api/sync-checkpoints",
        "/api/import-runs",
        "/api/validation-issues",
        "/api/matches/10/notes",
        "/api/notes/1",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/unknown",
        "/api/matches/",
        "/api/matches/%31%30",
        "/api/matches/10%2Fchanges",
    )

    for path in denied_paths:
        assert client.get(path).status_code == 404, path

    for method in ("post", "put", "patch", "delete", "options", "head"):
        response = getattr(client, method)("/api/matches/10")
        assert response.status_code == 404, method

    response = client.post(
        "/api/matches/10/notes",
        json={"note_text": "must not be written", "created_by": "public"},
        headers={"X-Notes-Token": "a-secure-local-token"},
    )
    assert response.status_code == 404
    assert repository.note["note_text"] == "Review lineup"


def test_public_readonly_allowlist_fails_closed_without_raw_path() -> None:
    request = SimpleNamespace(method="GET", scope={"path": "/api/matches/10"})

    assert not _is_public_readonly_request(request)


def test_public_readonly_mode_returns_generic_errors_without_internal_details() -> None:
    class BrokenRepository(FakeRepository):
        def competitions(self) -> list[dict[str, Any]]:
            raise RuntimeError("PWD=secret; C:\\private\\database; SQL text")

    client = _test_client(
        create_app(BrokenRepository(), _public_settings()),
        raise_server_exceptions=False,
    )

    response = client.get("/api/competitions")

    assert response.status_code == 500
    assert response.json() == {"detail": "The request could not be completed."}
    assert "secret" not in response.text
    assert "private" not in response.text
    assert "SQL text" not in response.text


def test_dashboard_shell_assets_and_data_contracts_are_served() -> None:
    repository = FakeRepository()
    client = _test_client(create_app(repository, _settings()))

    dashboard_response = client.get("/")
    script_response = client.get("/assets/app.js")
    stylesheet_response = client.get("/assets/styles.css")
    summary_response = client.get("/api/dashboard-summary?competition_season_id=1")
    freshness_response = client.get("/api/freshness?competition_season_id=1")
    changes_response = client.get("/api/match-changes?competition_season_id=1&limit=20")

    assert dashboard_response.status_code == 200
    assert "Overview" in dashboard_response.text
    assert "Insights" in dashboard_response.text
    assert 'href="#insights"' in dashboard_response.text
    assert 'id="insights"' in dashboard_response.text
    assert 'id="insights-source"' in dashboard_response.text
    assert "Match explorer" in dashboard_response.text
    assert "Change intelligence" in dashboard_response.text
    assert "Database service" not in dashboard_response.text
    assert "Database available" not in dashboard_response.text
    assert 'id="health"' not in dashboard_response.text
    assert 'class="service-card"' not in dashboard_response.text
    assert "Import &amp; sync monitor" not in dashboard_response.text
    assert 'href="#operations"' not in dashboard_response.text
    assert 'id="operations"' not in dashboard_response.text
    assert 'id="last-updated"' in dashboard_response.text
    assert "Last updated" in dashboard_response.text
    assert "/assets/styles.css?v=20261107-explorer-polish" in dashboard_response.text
    assert "/assets/app.js?v=20261107-explorer-polish" in dashboard_response.text
    nav_start = dashboard_response.text.index('<nav class="section-nav"')
    nav_end = dashboard_response.text.index("</nav>", nav_start)
    nav_markup = dashboard_response.text[nav_start:nav_end]
    navigation_order = [
        nav_markup.index('href="#overview"'),
        nav_markup.index('href="#match-explorer"'),
        nav_markup.index('href="#insights"'),
        nav_markup.index('href="#change-intelligence"'),
    ]
    assert navigation_order == sorted(navigation_order)
    assert "Verified source observations" not in dashboard_response.text
    assert (
        "Local-only application. Fixture facts come from preserved OpenLigaDB observations"
        not in dashboard_response.text
    )
    assert (
        "UTC API timestamps are displayed in this browser's local timezone"
        not in dashboard_response.text
    )
    assert 'rel="icon"' in dashboard_response.text
    assert 'id="fixture-sort"' in dashboard_response.text
    assert "All matches" in dashboard_response.text
    assert "Upcoming" in dashboard_response.text
    assert "Completed" in dashboard_response.text
    assert '<option value="true" selected>Completed</option>' in dashboard_response.text
    assert "Valid After90Minutes scores" not in dashboard_response.text
    assert "Matches with confirmed final scores" in dashboard_response.text
    assert 'id="upcoming-list"' in dashboard_response.text
    assert script_response.status_code == 200
    assert "javascript" in script_response.headers["content-type"]
    assert "/api/dashboard-summary" in script_response.text
    assert "/api/freshness" in script_response.text
    assert "/api/insights/summary" in script_response.text
    assert "/api/insights/teams" in script_response.text
    assert "/api/insights/matchdays" in script_response.text
    assert "latest_successful_sync_at_utc" in script_response.text
    assert "/api/match-changes" in script_response.text
    assert "latest_successful_sync_at_utc" in script_response.text
    assert 'request("/health")' not in script_response.text
    assert "loadHealth" not in script_response.text
    assert "database service" not in script_response.text.lower()
    assert "/api/import-runs" not in script_response.text
    assert "/api/sync-checkpoints" not in script_response.text
    assert "/api/validation-issues" not in script_response.text
    assert "loadOperations" not in script_response.text
    assert "operationsRequestId" not in script_response.text
    assert "DASHBOARD_SECTION_ORDER" in script_response.text
    assert "setupSectionNavigation" in script_response.text
    assert 'setAttribute("aria-current", "location")' in script_response.text
    assert 'sort: ui.sortSelect?.value || "explorer"' in script_response.text
    assert "function loadUpcomingFixtures" in script_response.text
    assert "function loadFreshness" in script_response.text
    assert 'apiPath("/api/freshness"' in script_response.text
    assert "state.freshnessRevision" in script_response.text
    assert "state.freshnessInitialized" in script_response.text
    assert "updateLastUpdatedTimestamp" in script_response.text
    assert "FRESHNESS_POLL_INTERVAL_MS = 60000" in script_response.text
    assert "function scheduleFreshnessPoll" in script_response.text
    assert "preserveChangePage: true" in script_response.text
    assert "visibilitychange" in script_response.text
    assert "finished: false" in script_response.text
    assert 'sort: "explorer"' in script_response.text
    assert "Kickoff to be confirmed" in script_response.text
    assert "function groupChangeEvents" in script_response.text
    assert "function changeEventSummary" in script_response.text
    assert "function detailChangeSection" in script_response.text
    assert "function detailChangeRow" not in script_response.text
    assert "Match completed" in script_response.text
    assert "Final score recorded" in script_response.text
    assert "Goal event added" in script_response.text
    assert "text: change.field_name" not in script_response.text
    assert "No fixtures match these filters" in script_response.text
    assert 'id="change-page-previous"' in dashboard_response.text
    assert 'id="change-page-next"' in dashboard_response.text
    assert "function renderChangePagination" in script_response.text
    assert "changePageSize: 25" in script_response.text
    assert "state.changeOffset >= page.total" in script_response.text
    assert "Completed matches first, then upcoming fixtures" in script_response.text
    assert 'ui.finishedSelect.value = "true"' in script_response.text
    assert "Source updated ${formatDate(match.last_source_update_utc)}" not in script_response.text
    assert "Source result type" not in script_response.text
    assert "function resultTypeLabel" in script_response.text
    assert "renderFixturePage(page)" in script_response.text
    assert "changeRequestId" in script_response.text
    assert "matchdayRequestId" in script_response.text
    assert "overviewRequestId" in script_response.text
    assert stylesheet_response.status_code == 200
    assert "text/css" in stylesheet_response.headers["content-type"]
    assert ".metric-grid" in stylesheet_response.text
    assert ".insight-summary-grid" in stylesheet_response.text
    assert ".insight-chart" in stylesheet_response.text
    assert ".insight-table" in stylesheet_response.text
    assert ".upcoming-fixture" in stylesheet_response.text
    assert ".fixture-card-topline" in stylesheet_response.text
    assert ".fixture-teams" in stylesheet_response.text
    assert ".detail-row > *" in stylesheet_response.text
    assert ".pagination" in stylesheet_response.text
    assert ".last-updated" in stylesheet_response.text
    assert ".freshness-check" in stylesheet_response.text
    assert '.nav-links a[aria-current="location"]' in stylesheet_response.text
    assert ".service-card" not in stylesheet_response.text
    assert ".service-status" not in stylesheet_response.text
    assert ".operations-grid" not in stylesheet_response.text
    assert ".change-field-row" in stylesheet_response.text
    assert ".detail-change-event-list" in stylesheet_response.text
    assert summary_response.json()["goals_recorded"] == 74

    assert summary_response.json()["detected_changes"] == 1
    assert summary_response.json()["changed_fixtures"] == 1
    assert summary_response.json()["latest_successful_import_run_id"] == 3
    assert freshness_response.status_code == 200
    assert freshness_response.json() == {
        "revision": "revision-3",
        "latest_successful_sync_at_utc": "2026-11-03T00:00:00Z",
    }
    assert repository.last_summary_competition_id == 1
    change_page = changes_response.json()
    assert change_page["total"] == 1
    assert change_page["items"][0]["snapshot_sha256"] == "a" * 64
    assert repository.last_change_filters == {
        "competition_season_id": 1,
        "limit": 20,
        "offset": 0,
    }


def test_health_endpoint_remains_available_for_internal_monitoring() -> None:
    client = _test_client(create_app(FakeRepository(), _settings()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "available"}


def test_insight_routes_return_typed_read_only_analytics() -> None:
    client = _test_client(create_app(FakeRepository(), _settings()))

    summary = client.get("/api/insights/summary?competition_season_id=1")
    teams = client.get("/api/insights/teams?competition_season_id=1")
    matchdays = client.get("/api/insights/matchdays?competition_season_id=1")
    detail = client.get("/api/insights/teams/101?competition_season_id=1")

    assert summary.status_code == 200
    assert summary.json()["completed_matches_with_valid_final_score"] == 1
    assert summary.json()["full_time_goals"] == 3
    assert summary.json()["most_goals_teams"][0]["matches_played"] == 1
    assert teams.status_code == 200
    assert teams.json()[0]["provider_team_id"] == 101
    assert teams.json()[0]["recent_form"] == ["W"]
    assert matchdays.status_code == 200
    assert matchdays.json()[0]["full_time_goals"] == 3
    assert detail.status_code == 200
    assert detail.json()["recent_matches"][0]["outcome"] == "W"


def test_insights_frontend_paths_match_registered_fastapi_routes() -> None:
    application = create_app(FakeRepository(), _settings())
    client = _test_client(application)
    dashboard = client.get("/")
    script = client.get("/assets/app.js")

    assert dashboard.status_code == 200
    assert script.status_code == 200
    registered_paths = {route.path for route in application.routes if getattr(route, "path", None)}
    assert {
        "/api/insights/summary",
        "/api/insights/teams",
        "/api/insights/matchdays",
        "/api/insights/teams/{team_id}",
        "/api/freshness",
    } <= registered_paths
    for path in (
        "/api/insights/summary",
        "/api/insights/teams",
        "/api/insights/matchdays",
    ):
        assert f'apiPath("{path}"' in script.text
    assert "apiPath(`/api/insights/teams/${teamId}`" in script.text


def test_unknown_insight_team_returns_not_found() -> None:
    client = _test_client(create_app(FakeRepository(), _settings()))

    response = client.get("/api/insights/teams/999?competition_season_id=1")

    assert response.status_code == 404


def test_dashboard_data_routes_preserve_empty_state_contracts() -> None:
    repository = FakeRepository()

    def empty_matches(**filters: Any) -> tuple[list[dict[str, Any]], int]:
        del filters
        return [], 0

    def empty_summary(competition_season_id: int | None) -> dict[str, Any]:
        del competition_season_id
        return {
            "total_fixtures": 0,
            "finished_fixtures": 0,
            "upcoming_fixtures": 0,
            "goals_recorded": 0,
            "detected_changes": 0,
            "changed_fixtures": 0,
            "latest_successful_sync_at_utc": None,
            "latest_successful_snapshot_id": None,
            "latest_successful_import_run_id": None,
        }

    def empty_changes(**filters: Any) -> tuple[list[dict[str, Any]], int]:
        del filters
        return [], 0

    repository.matches = empty_matches  # type: ignore[method-assign]
    repository.dashboard_summary = empty_summary  # type: ignore[method-assign]
    repository.match_changes = empty_changes  # type: ignore[method-assign]
    client = _test_client(create_app(repository, _settings()))

    assert client.get("/api/matches").json() == {
        "items": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }
    assert client.get("/api/dashboard-summary").json()["total_fixtures"] == 0
    assert client.get("/api/match-changes").json() == {
        "items": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }


def test_match_detail_preserves_typed_results() -> None:
    client = _test_client(create_app(FakeRepository(), _settings()))

    response = client.get("/api/matches/10")

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["result_type"] == "After90Minutes"
    assert result["home_score"] == 2


def test_match_change_history_keeps_field_level_data_and_provenance() -> None:
    client = _test_client(create_app(FakeRepository(), _settings()))

    response = client.get("/api/matches/10/changes")

    assert response.status_code == 200
    changes = response.json()
    assert {change["field_name"] for change in changes} == {
        "source_match_is_finished",
        "result.2002.result_type_kind",
        "result.2002.points_team1",
        "goal.152095.goal_getter_provider_id",
    }
    assert {change["change_kind"] for change in changes} == {"Inserted", "Updated"}
    assert {change["source_snapshot_id"] for change in changes} == {8}
    assert {change["import_run_id"] for change in changes} == {3}


def test_match_detail_accepts_genuinely_missing_result_and_goal_scores() -> None:
    repository = FakeRepository()
    original_match = repository.match

    def nullable_match(match_id: int) -> dict[str, Any] | None:
        record = original_match(match_id)
        if record is None:
            return None
        record["results"][0]["home_score"] = None
        record["results"][0]["away_score"] = None
        record["goals"] = [
            {
                "provider_goal_id": 99,
                "score_home": None,
                "score_away": None,
                "minute": None,
            }
        ]
        return record

    repository.match = nullable_match  # type: ignore[method-assign]
    response = _test_client(create_app(repository, _settings())).get("/api/matches/10")

    assert response.status_code == 200
    assert response.json()["results"][0]["home_score"] is None
    assert response.json()["goals"][0]["score_home"] is None


def test_missing_match_is_404() -> None:
    client = _test_client(create_app(FakeRepository(), _settings()))

    response = client.get("/api/matches/999")

    assert response.status_code == 404


def test_non_positive_path_ids_are_rejected_before_repository_access() -> None:
    client = _test_client(create_app(FakeRepository(), _settings()))

    responses = [
        client.get("/api/matches/0"),
        client.get("/api/matches/-1/changes"),
        client.get("/api/matches/0/notes"),
    ]

    assert all(response.status_code == 422 for response in responses)
    assert all("not-a-real-secret" not in response.text for response in responses)


def test_note_writes_are_disabled_by_default() -> None:
    client = _test_client(create_app(FakeRepository(), _settings()))

    response = client.post(
        "/api/matches/10/notes",
        json={"note_text": "Do not write", "created_by": "tester"},
    )

    assert response.status_code == 403


def test_note_write_requires_correct_token() -> None:
    client = _test_client(create_app(FakeRepository(), _settings(writes=True)))
    body = {"note_text": "Review lineup", "created_by": "tester"}

    rejected = client.post("/api/matches/10/notes", json=body)
    accepted = client.post(
        "/api/matches/10/notes",
        json=body,
        headers={"X-Notes-Token": "a-secure-local-token"},
    )

    assert rejected.status_code == 403
    assert accepted.status_code == 201
    assert accepted.json()["note_text"] == "Review lineup"


def test_note_update_and_archive_require_token_and_preserve_soft_delete() -> None:
    repository = FakeRepository()
    client = _test_client(create_app(repository, _settings(writes=True)))
    headers = {"X-Notes-Token": "a-secure-local-token"}

    updated = client.put(
        "/api/notes/1",
        json={"note_text": "Updated note"},
        headers=headers,
    )
    archived = client.delete("/api/notes/1", headers=headers)

    assert updated.status_code == 200
    assert updated.json()["note_text"] == "Updated note"
    assert archived.status_code == 204
    assert repository.note["is_archived"] is True
    assert client.get("/api/matches/10/notes").json() == []


def test_unhandled_repository_error_returns_generic_response() -> None:
    repository = FakeRepository()

    def fail(**filters: Any):
        del filters
        raise RuntimeError("internal SQL detail; PWD=not-a-real-secret")

    repository.matches = fail  # type: ignore[method-assign]
    client = _test_client(
        create_app(repository, _settings()),
        raise_server_exceptions=False,
    )

    response = client.get("/api/matches")

    assert response.status_code == 500
    assert response.json() == {"detail": "The request could not be completed."}
    assert "not-a-real-secret" not in response.text
