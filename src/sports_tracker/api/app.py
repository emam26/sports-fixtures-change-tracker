"""FastAPI application factory with local-only defaults."""

import hmac
import ipaddress
import logging
from pathlib import Path
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi import (
    Path as PathParameter,
)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sports_tracker.analytics import AnalyticsService
from sports_tracker.api.models import (
    Competition,
    DashboardFreshness,
    DashboardSummary,
    Health,
    ImportRun,
    InsightSummary,
    MatchChange,
    MatchChangePage,
    MatchdayInsight,
    MatchdaySummary,
    MatchDetail,
    MatchPage,
    Note,
    NoteCreate,
    NoteUpdate,
    ServiceStatus,
    SyncCheckpoint,
    TeamInsight,
    TeamInsightDetail,
    ValidationIssue,
)
from sports_tracker.api.repository import MatchSort, Repository, SQLServerRepository
from sports_tracker.config import ApplicationSettings, load_application_settings
from sports_tracker.runtime import open_sql_server_connection

_LOGGER = logging.getLogger(__name__)


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def create_app(
    repository: Repository | None = None,
    settings: ApplicationSettings | None = None,
) -> FastAPI:
    app_settings = settings or load_application_settings()
    repo = repository or SQLServerRepository(open_sql_server_connection)
    web_directory = Path(__file__).resolve().parent.parent / "web"
    app = FastAPI(
        title="Sports Fixtures & Change Tracker",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.repository = repo
    app.state.settings = app_settings
    analytics = AnalyticsService(repo)

    @app.exception_handler(Exception)
    async def unhandled_error(_request: Request, exc: Exception) -> JSONResponse:
        _LOGGER.error("Unhandled API error (%s)", type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "The request could not be completed."},
        )

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        client_host = request.client.host if request.client else None
        if app_settings.local_only and not _is_loopback(client_host):
            return Response(
                content="Local access only",
                status_code=status.HTTP_403_FORBIDDEN,
                media_type="text/plain",
            )
        return await call_next(request)

    def get_repository() -> Repository:
        return app.state.repository

    def permit_note_write(
        x_notes_token: Annotated[str | None, Header()] = None,
    ) -> None:
        if not app_settings.allow_note_writes:
            raise HTTPException(status_code=403, detail="Note writes are disabled")
        expected = app_settings.notes_write_token
        if expected is None or x_notes_token is None:
            raise HTTPException(status_code=403, detail="A note-write token is required")
        if not hmac.compare_digest(expected, x_notes_token):
            raise HTTPException(status_code=403, detail="Invalid note-write token")

    RepositoryDependency = Annotated[Repository, Depends(get_repository)]
    Limit = Annotated[int, Query(ge=1, le=200)]
    Offset = Annotated[int, Query(ge=0)]
    PositiveId = Annotated[int, PathParameter(ge=1)]

    @app.get("/health", response_model=Health)
    def health(repository: RepositoryDependency) -> Health:
        try:
            repository.health()
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Database unavailable") from exc
        return Health(status="ok", database="available")

    @app.get("/api/status", response_model=ServiceStatus)
    def service_status() -> ServiceStatus:
        return ServiceStatus(
            status="ok",
            local_only=app_settings.local_only,
            note_writes_enabled=app_settings.allow_note_writes,
        )

    @app.get("/api/competitions", response_model=list[Competition])
    def competitions(repository: RepositoryDependency):
        return repository.competitions()

    @app.get("/api/matchdays", response_model=list[MatchdaySummary])
    def matchdays(
        repository: RepositoryDependency,
        competition_season_id: Annotated[int | None, Query(ge=1)] = None,
    ):
        return repository.matchdays(competition_season_id)

    @app.get("/api/matches", response_model=MatchPage)
    def matches(
        repository: RepositoryDependency,
        competition_season_id: Annotated[int | None, Query(ge=1)] = None,
        matchday: Annotated[int | None, Query(ge=1)] = None,
        finished: bool | None = None,
        search: Annotated[str | None, Query(max_length=200)] = None,
        limit: Limit = 50,
        offset: Offset = 0,
        sort: MatchSort = "explorer",
    ) -> MatchPage:
        items, total = repository.matches(
            competition_season_id=competition_season_id,
            matchday=matchday,
            finished=finished,
            search=search.strip() if search else None,
            limit=limit,
            offset=offset,
            sort=sort,
        )
        return MatchPage(items=items, total=total, limit=limit, offset=offset)

    @app.get("/api/dashboard-summary", response_model=DashboardSummary)
    def dashboard_summary(
        repository: RepositoryDependency,
        competition_season_id: Annotated[int | None, Query(ge=1)] = None,
    ) -> DashboardSummary:
        return repository.dashboard_summary(competition_season_id)

    @app.get("/api/freshness", response_model=DashboardFreshness)
    def freshness(
        repository: RepositoryDependency,
        competition_season_id: Annotated[int | None, Query(ge=1)] = None,
    ) -> DashboardFreshness:
        return repository.freshness(competition_season_id)

    @app.get("/api/insights/summary", response_model=InsightSummary)
    def insights_summary(
        competition_season_id: Annotated[int | None, Query(ge=1)] = None,
    ) -> InsightSummary:
        return analytics.summary(competition_season_id)

    @app.get("/api/insights/teams", response_model=list[TeamInsight])
    def insights_teams(
        competition_season_id: Annotated[int | None, Query(ge=1)] = None,
    ) -> list[TeamInsight]:
        return analytics.teams(competition_season_id)

    @app.get("/api/insights/matchdays", response_model=list[MatchdayInsight])
    def insights_matchdays(
        competition_season_id: Annotated[int | None, Query(ge=1)] = None,
    ) -> list[MatchdayInsight]:
        return analytics.matchdays(competition_season_id)

    @app.get("/api/insights/teams/{team_id}", response_model=TeamInsightDetail)
    def insights_team(
        team_id: PositiveId,
        competition_season_id: Annotated[int | None, Query(ge=1)] = None,
    ) -> TeamInsightDetail:
        record = analytics.team(competition_season_id, team_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Team insight not found")
        return TeamInsightDetail.model_validate(record)

    @app.get("/api/matches/{match_id}", response_model=MatchDetail)
    def match(match_id: PositiveId, repository: RepositoryDependency):
        record = repository.match(match_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Match not found")
        return record

    @app.get("/api/matches/{match_id}/changes", response_model=list[MatchChange])
    def changes(match_id: PositiveId, repository: RepositoryDependency):
        return repository.changes(match_id)

    @app.get("/api/match-changes", response_model=MatchChangePage)
    def match_changes(
        repository: RepositoryDependency,
        competition_season_id: Annotated[int | None, Query(ge=1)] = None,
        limit: Limit = 50,
        offset: Offset = 0,
    ) -> MatchChangePage:
        items, total = repository.match_changes(
            competition_season_id=competition_season_id,
            limit=limit,
            offset=offset,
        )
        return MatchChangePage(items=items, total=total, limit=limit, offset=offset)

    @app.get("/api/sync-checkpoints", response_model=list[SyncCheckpoint])
    def sync_checkpoints(
        repository: RepositoryDependency,
        limit: Limit = 50,
        offset: Offset = 0,
    ):
        items, _ = repository.sync_checkpoints(limit, offset)
        return items

    @app.get("/api/import-runs", response_model=list[ImportRun])
    def import_runs(
        repository: RepositoryDependency,
        limit: Limit = 50,
        offset: Offset = 0,
    ):
        items, _ = repository.import_runs(limit, offset)
        return items

    @app.get("/api/validation-issues", response_model=list[ValidationIssue])
    def validation_issues(
        repository: RepositoryDependency,
        limit: Limit = 50,
        offset: Offset = 0,
    ):
        items, _ = repository.validation_issues(limit, offset)
        return items

    @app.get("/api/matches/{match_id}/notes", response_model=list[Note])
    def notes(match_id: PositiveId, repository: RepositoryDependency):
        return repository.notes(match_id)

    @app.post(
        "/api/matches/{match_id}/notes",
        response_model=Note,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(permit_note_write)],
    )
    def create_note(
        match_id: PositiveId,
        body: NoteCreate,
        repository: RepositoryDependency,
    ):
        if repository.match(match_id) is None:
            raise HTTPException(status_code=404, detail="Match not found")
        return repository.create_note(match_id, body.note_text.strip(), body.created_by.strip())

    @app.put(
        "/api/notes/{note_id}",
        response_model=Note,
        dependencies=[Depends(permit_note_write)],
    )
    def update_note(
        note_id: PositiveId,
        body: NoteUpdate,
        repository: RepositoryDependency,
    ):
        record = repository.update_note(note_id, body.note_text.strip())
        if record is None:
            raise HTTPException(status_code=404, detail="Note not found")
        return record

    @app.delete(
        "/api/notes/{note_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(permit_note_write)],
    )
    def archive_note(
        note_id: PositiveId,
        repository: RepositoryDependency,
    ) -> Response:
        if not repository.archive_note(note_id):
            raise HTTPException(status_code=404, detail="Note not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    app.mount("/assets", StaticFiles(directory=web_directory), name="assets")

    @app.get("/", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(web_directory / "index.html")

    return app
