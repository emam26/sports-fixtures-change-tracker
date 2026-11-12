from __future__ import annotations

from typing import Any

import pytest
from scripts import migrate_sqlserver_to_postgres as migration


class _Cursor:
    description: tuple[tuple[str], ...] = ()
    rowcount = 0

    def __init__(self, *, fail_on_sequence_alignment: bool = False) -> None:
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.fail_on_sequence_alignment = fail_on_sequence_alignment

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, parameters: tuple[Any, ...] = ()) -> None:
        self.statements.append((statement, parameters))
        if self.fail_on_sequence_alignment and "setval" in statement.lower():
            raise RuntimeError("sequence alignment failed")

    def fetchall(self) -> list[tuple[Any, ...]]:
        return []

    def fetchone(self) -> tuple[int]:
        return (0,)

    def close(self) -> None:
        return None


class _Connection:
    def __init__(self, *, fail_on_sequence_alignment: bool = False) -> None:
        self.cursor_instance = _Cursor(fail_on_sequence_alignment=fail_on_sequence_alignment)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> _Cursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _ConnectionContext:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def __enter__(self) -> _Connection:
        return self.connection

    def __exit__(self, *_args: object) -> None:
        return None


def _patch_migration_connections(
    monkeypatch: pytest.MonkeyPatch,
    source: _Connection,
    target: _Connection,
) -> None:
    monkeypatch.setattr(migration, "load_database_settings", lambda: object())
    monkeypatch.setattr(migration, "load_postgresql_settings", lambda: object())
    monkeypatch.setattr(
        migration,
        "database_connection",
        lambda *_args, **_kwargs: _ConnectionContext(source),
    )
    monkeypatch.setattr(
        migration,
        "postgresql_connection",
        lambda *_args, **_kwargs: _ConnectionContext(target),
    )


def test_apply_commits_after_sequence_alignment_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _Connection()
    target = _Connection()
    _patch_migration_connections(monkeypatch, source, target)

    migration.reconcile_and_migrate(apply=True, schema="public")

    assert target.commits == 1
    assert target.rollbacks == 0
    sequence_statements = [
        (statement, parameters)
        for statement, parameters in target.cursor_instance.statements
        if "setval" in statement.lower()
    ]
    assert len(sequence_statements) == len(migration.TABLE_SPECS)
    for (_, parameters), (_, primary_key, _) in zip(
        sequence_statements, migration.TABLE_SPECS, strict=True
    ):
        assert parameters[-1] == primary_key


def test_apply_rolls_back_when_sequence_alignment_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _Connection()
    target = _Connection(fail_on_sequence_alignment=True)
    _patch_migration_connections(monkeypatch, source, target)

    with pytest.raises(RuntimeError, match="sequence alignment failed"):
        migration.reconcile_and_migrate(apply=True, schema="public")

    assert target.commits == 0
    assert target.rollbacks == 1


def test_preview_rolls_back_without_committing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _Connection()
    target = _Connection()
    _patch_migration_connections(monkeypatch, source, target)

    migration.reconcile_and_migrate(apply=False, schema="public")

    assert target.commits == 0
    assert target.rollbacks == 1
