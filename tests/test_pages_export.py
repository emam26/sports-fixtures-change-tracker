from dataclasses import replace
from types import SimpleNamespace

import pytest

from sports_tracker import pages_export
from sports_tracker.config import OpenLigaDBSettings
from sports_tracker.ingestion import ValidationIssue
from sports_tracker.pages_export import PagesExportError

REVIEWED_VARIANTS = "resultID 129519: 2-0; resultID 129520: 0-0"


@pytest.mark.parametrize(
    ("match_id", "variants", "use_recovery"),
    [
        ("87412", REVIEWED_VARIANTS, True),
        ("87413", REVIEWED_VARIANTS, False),
        ("87412", "resultID 129519: 1-0; resultID 129520: 0-0", False),
    ],
)
def test_pages_allows_only_reviewed_halftime_conflict(
    monkeypatch,
    tmp_path,
    match_id,
    variants,
    use_recovery,
):
    source = OpenLigaDBSettings("https://api.openligadb.de", "ucl", 2026, 4946, 10, tmp_path)
    strict = SimpleNamespace(
        metadata=SimpleNamespace(matchday=2),
        errors=(ValidationIssue("duplicate-result-type", "conflict"),),
    )
    recovered = SimpleNamespace(
        metadata=strict.metadata,
        errors=(),
        matches=list(range(18)),
        issues=(
            ValidationIssue(
                "conflicting-nonfinal-result-quarantined",
                "quarantined",
                source_record_id=match_id,
                source_value=variants,
            ),
        ),
    )

    def load_snapshot(directory, settings, *, allow_conflicting_nonfinal_results=False):
        assert directory == tmp_path
        assert settings == source
        return recovered if allow_conflicting_nonfinal_results else strict

    monkeypatch.setattr(pages_export, "load_snapshot", load_snapshot)
    assert pages_export.load_pages_snapshot(tmp_path, source) is (
        recovered if use_recovery else strict
    )
    if use_recovery:
        incomplete = replace(source, expected_fixtures_per_matchday=19)
        monkeypatch.setattr(
            pages_export,
            "load_snapshot",
            lambda *_args, **kw: (
                recovered if kw.get("allow_conflicting_nonfinal_results") else strict
            ),
        )
        with pytest.raises(PagesExportError, match="unexpected fixture coverage"):
            pages_export.load_pages_snapshot(tmp_path, incomplete)


def test_export_rejects_incomplete_sql_pages():
    rows = [{"match_change_id": index} for index in range(201)]
    seen = []

    def query(*, limit, offset):
        seen.append(offset)
        return (rows[offset : offset + limit], 201)

    assert pages_export._complete_pages(query) == rows
    assert seen == [0, 200]

    with pytest.raises(PagesExportError, match="SQL page rows"):
        pages_export._complete_pages(lambda **_: ([], 201))
