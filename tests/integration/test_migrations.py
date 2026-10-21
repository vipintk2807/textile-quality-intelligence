"""The Alembic migration must create exactly the schema the models describe."""

import sqlite3

from flask_migrate import upgrade

from tests.integration.conftest import build_app


def test_upgrade_creates_all_tables_and_matches_models(tmp_path, monkeypatch):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.extensions import db

    app = build_app(tmp_path, monkeypatch)
    with app.app_context():
        upgrade()
        con = sqlite3.connect(tmp_path / "test.db")
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        assert {"inspections", "defect_entries", "disposition_records", "corrective_actions",
                "action_follow_ups", "defect_categories", "severity_levels", "alembic_version"} <= tables

        with db.engine.connect() as connection:
            diff = compare_metadata(MigrationContext.configure(connection), db.metadata)
        assert diff == [], f"Migration and models disagree: {diff}"
        db.session.remove()
        db.engine.dispose()
