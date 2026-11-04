from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from sports_tracker.api.app import create_app
from sports_tracker.config import ApplicationSettings


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

    def matches(self, **filters: Any) -> tuple[list[dict[str, Any]], int]:
        self.last_filters = filters
        return [self._match()], 1

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
        return []

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
        local_only=False,
        allow_note_writes=writes,
        notes_write_token="a-secure-local-token" if writes else None,
    )


def test_match_filters_are_validated_and_forwarded() -> None:
    repository = FakeRepository()
    client = TestClient(create_app(repository, _settings()))

    response = client.get("/api/matches?matchday=3&finished=true&search=Alpha")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert repository.last_filters["matchday"] == 3
    assert repository.last_filters["finished"] is True
    assert repository.last_filters["search"] == "Alpha"


def test_match_detail_preserves_typed_results() -> None:
    client = TestClient(create_app(FakeRepository(), _settings()))

    response = client.get("/api/matches/10")

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["result_type"] == "After90Minutes"
    assert result["home_score"] == 2


def test_missing_match_is_404() -> None:
    client = TestClient(create_app(FakeRepository(), _settings()))

    response = client.get("/api/matches/999")

    assert response.status_code == 404


def test_note_writes_are_disabled_by_default() -> None:
    client = TestClient(create_app(FakeRepository(), _settings()))

    response = client.post(
        "/api/matches/10/notes",
        json={"note_text": "Do not write", "created_by": "tester"},
    )

    assert response.status_code == 403


def test_note_write_requires_correct_token() -> None:
    client = TestClient(create_app(FakeRepository(), _settings(writes=True)))
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
