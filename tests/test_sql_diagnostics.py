from __future__ import annotations

from types import SimpleNamespace

import pytest

from sports_tracker.ingestion import SQLServerImportStore, SQLServerOperationError


class _FailingCursor:
    def execute(self, statement: str, parameters: tuple[object, ...]) -> None:
        del statement, parameters
        raise RuntimeError("SQL login failed; PWD={not-a-real-password;still-secret}; state=28000")


class _FailingConnection:
    def cursor(self) -> _FailingCursor:
        return _FailingCursor()


class _ResultSequenceCursor:
    def __init__(self, result_sets: tuple[tuple[object, ...] | None, ...]) -> None:
        self._result_sets = result_sets
        self._current_index = 0
        self.nextset_calls = 0

    @property
    def description(self) -> tuple[tuple[str], ...] | None:
        if self._result_sets[self._current_index] is None:
            return None
        return (("identity",),)

    def execute(self, statement: str, parameters: tuple[object, ...]) -> _ResultSequenceCursor:
        del statement, parameters
        return self

    def nextset(self) -> bool:
        self.nextset_calls += 1
        if self._current_index + 1 >= len(self._result_sets):
            return False
        self._current_index += 1
        return True

    def fetchone(self) -> tuple[object, ...]:
        current = self._result_sets[self._current_index]
        if current is None:
            raise RuntimeError("No results. Previous SQL was not a query.")
        return current


class _ResultSequenceConnection:
    def __init__(self, result_sets: tuple[tuple[object, ...] | None, ...]) -> None:
        self.cursor_instance = _ResultSequenceCursor(result_sets)

    def cursor(self) -> _ResultSequenceCursor:
        return self.cursor_instance


class _ProvenanceConnection:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


def test_sql_operation_diagnostic_names_operation_and_redacts_password() -> None:
    store = SQLServerImportStore(_FailingConnection())

    with pytest.raises(SQLServerOperationError) as failure:
        store.ensure_competition("OpenLigaDB", "ucl", "UEFA Champions League")

    assert failure.value.operation == "SQLServerImportStore.ensure_competition"
    assert "not-a-real-password" not in str(failure.value)
    assert "still-secret" not in str(failure.value)
    assert "PWD=<redacted>" in str(failure.value)


def test_insert_id_advances_past_intermediate_non_row_results() -> None:
    connection = _ResultSequenceConnection((None, None, (73,)))
    store = SQLServerImportStore(connection)

    inserted_id = store._insert_id("INSERT ...; SELECT SCOPE_IDENTITY();", ())

    assert inserted_id == 73
    assert connection.cursor_instance.nextset_calls == 2


def test_insert_id_rejects_batches_without_an_identity_result_set() -> None:
    connection = _ResultSequenceConnection((None,))
    store = SQLServerImportStore(connection)

    with pytest.raises(RuntimeError, match="identity result set"):
        store._insert_id("INSERT ...", ())


def test_failed_run_provenance_does_not_repeat_the_primary_rollback(monkeypatch) -> None:
    connection = _ProvenanceConnection()
    store = SQLServerImportStore(connection)
    parsed = SimpleNamespace(
        metadata=SimpleNamespace(provider="OpenLigaDB", shortcut="ucl", season=2026),
        competition_name="UEFA Champions League",
        source_league_id=4946,
        matches=(),
    )
    monkeypatch.setattr(store, "ensure_snapshot", lambda _parsed: 1)
    monkeypatch.setattr(store, "ensure_competition", lambda _provider, _shortcut, _name: 2)
    monkeypatch.setattr(store, "ensure_season", lambda _competition_id, _league_id, _season: 3)
    monkeypatch.setattr(store, "find_successful_run", lambda _snapshot_id: None)
    monkeypatch.setattr(
        store,
        "start_run",
        lambda _parsed, _season_id, _snapshot_id, _is_replay, _replay_of: 4,
    )
    monkeypatch.setattr(store, "record_issues", lambda _run_id, _snapshot_id, _issues: None)
    monkeypatch.setattr(
        store,
        "finish_run",
        lambda _run_id, _status, _counters, _phase, _summary: None,
    )

    store.record_failed_run(parsed, "safe failure summary")

    assert connection.rollback_calls == 0
    assert connection.commit_calls == 1


def test_failed_run_provenance_rolls_back_its_own_partial_transaction(monkeypatch) -> None:
    connection = _ProvenanceConnection()
    store = SQLServerImportStore(connection)

    def fail_to_record(_parsed):
        raise RuntimeError("synthetic provenance failure")

    monkeypatch.setattr(store, "ensure_snapshot", fail_to_record)

    with pytest.raises(RuntimeError, match="synthetic provenance failure"):
        store.record_failed_run(object(), "safe failure summary")

    assert connection.rollback_calls == 1
    assert connection.commit_calls == 0
