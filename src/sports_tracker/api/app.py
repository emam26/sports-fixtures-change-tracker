"""FastAPI application factory with local-only defaults."""

import hmac
import ipaddress
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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sports_tracker.api.models import (
    Competition,
    Health,
    ImportRun,
    MatchChange,
    MatchDetail,
    MatchPage,
    Note,
    NoteCreate,
    NoteUpdate,
    ValidationIssue,
)
from sports_tracker.api.repository import Repository, SQLServerRepository
from sports_tracker.config import ApplicationSettings, load_application_settings
from sports_tracker.runtime import open_sql_server_connection


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

    @app.get("/health", response_model=Health)
    def health(repository: RepositoryDependency) -> Health:
        try:
            repository.health()
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Database unavailable") from exc
        return Health(status="ok", database="available")

    @app.get("/api/competitions", response_model=list[Competition])
    def competitions(repository: RepositoryDependency):
        return repository.competitions()

    @app.get("/api/matches", response_model=MatchPage)
    def matches(
        repository: RepositoryDependency,
        competition_season_id: Annotated[int | None, Query(ge=1)] = None,
        matchday: Annotated[int | None, Query(ge=1)] = None,
        finished: bool | None = None,
        search: Annotated[str | None, Query(max_length=200)] = None,
        limit: Limit = 50,
        offset: Offset = 0,
    ) -> MatchPage:
        items, total = repository.matches(
            competition_season_id=competition_season_id,
            matchday=matchday,
            finished=finished,
            search=search.strip() if search else None,
            limit=limit,
            offset=offset,
        )
        return MatchPage(items=items, total=total, limit=limit, offset=offset)

    @app.get("/api/matches/{match_id}", response_model=MatchDetail)
    def match(match_id: int, repository: RepositoryDependency):
        record = repository.match(match_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Match not found")
        return record

    @app.get("/api/matches/{match_id}/changes", response_model=list[MatchChange])
    def changes(match_id: int, repository: RepositoryDependency):
        return repository.changes(match_id)

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
    def notes(match_id: int, repository: RepositoryDependency):
        return repository.notes(match_id)

    @app.post(
        "/api/matches/{match_id}/notes",
        response_model=Note,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(permit_note_write)],
    )
    def create_note(
        match_id: int,
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
        note_id: int,
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
        note_id: int,
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
