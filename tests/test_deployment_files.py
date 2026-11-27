"""Offline checks for deployment files; without contacting cloud services."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_render_configuration_is_public_readonly_and_does_not_contain_credentials() -> None:
    text = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "public_readonly" in text
    assert "0.0.0.0" in text
    assert "$PORT" in text
    assert "POSTGRES_DATABASE_URL" in text
    assert "sync: false" in text
    assert "password" not in text.lower()


def test_scheduled_workflow_is_concurrent_safe_and_object_storage_fail_closed() -> None:
    text = (ROOT / ".github" / "workflows" / "synchronize.yml").read_text(encoding="utf-8")
    assert 'cron: "17 2 * * *"' in text
    assert "cancel-in-progress: false" in text
    assert "workflow_dispatch" in text
    assert "RAW_SNAPSHOT_STORAGE: object" in text
    assert "needs: synchronize" in text
    assert "uses: actions/upload-pages-artifact@" in text
    assert "uses: actions/deploy-pages@" in text
    assert "secrets.POSTGRES_SYNC_DATABASE_URL" in text
    assert "github.ref_name == github.event.repository.default_branch" in text
    assert "git push" not in text


def test_postgresql_schema_contains_the_logical_tables_and_migration_ledger() -> None:
    text = (ROOT / "sql" / "postgresql" / "001_initial_schema.sql").read_text(encoding="utf-8")
    for table in (
        "competitions",
        "competition_seasons",
        "teams",
        "source_snapshots",
        "matches",
        "match_results",
        "match_goals",
        "import_runs",
        "validation_issues",
        "match_changes",
        "sync_checkpoints",
        "match_notes",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text
    assert "schema_migrations" in text
