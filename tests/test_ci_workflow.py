from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_runs_only_offline_quality_checks() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "ruff check ." in workflow
    assert "ruff format --check ." in workflow
    assert 'pytest -q -m "not sqlserver and not neon"' in workflow
    assert "sync_openligadb.py" not in workflow
    assert "POSTGRES" not in workflow
