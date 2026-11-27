from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_runs_only_offline_quality_checks() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    quality_job, archive_job = workflow.split("\n  postgres-archive:\n", maxsplit=1)

    assert "ruff check ." in quality_job
    assert "ruff format --check ." in quality_job
    assert 'pytest -q -m "not sqlserver and not neon and not postgres_archive"' in quality_job
    assert "POSTGRES" not in quality_job
    assert "sync_openligadb.py" not in workflow
    assert "secrets." not in workflow

    # Integration uses its own disposable service, never the production database.
    assert "image: postgres:17" in archive_job
    assert "POSTGRES_DB: archive_test" in archive_job
    assert "127.0.0.1:5432/archive_test" in archive_job
    assert "python -m pytest -q -m postgres_archive" in archive_job
    assert 'RUN_POSTGRES_ARCHIVE_TESTS: "yes"' in archive_job
