"""Integration-test fixtures. They need the full dependency set (pip install -r requirements-dev.txt)."""

from __future__ import annotations

import pytest

pytest.importorskip("flask_sqlalchemy")
pytest.importorskip("flask_migrate")
pytest.importorskip("flask_wtf")


def build_app(tmp_path, monkeypatch, *, csrf: bool = False):
    from app import create_app

    monkeypatch.setenv("TQI_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("TQI_DATABASE_PATH", str(tmp_path / "test.db"))
    return create_app(
        {"TQI_ENV": "testing", "WTF_CSRF_ENABLED": csrf, "BACKUP_DIR": str(tmp_path / "backups")}
    )


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from app.extensions import db

    application = build_app(tmp_path, monkeypatch)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def reference(app):
    """Two categories and two severities created through the service layer."""
    from app.services import defect_service as ds

    return {
        "hole": ds.create_category({"name": "Hole"}),
        "stain": ds.create_category({"name": "Stain"}),
        "minor": ds.create_severity({"name": "Minor", "sort_order": "1"}),
        "major": ds.create_severity({"name": "Major", "sort_order": "2"}),
    }


def inspection_form(**overrides):
    data = {
        "inspection_date": "2026-10-01",
        "product_reference": "Cotton twill",
        "batch_reference": "B-100",
        "production_stage": "Weaving",
        "inspected_quantity": "1000",
        "quantity_unit": "Meters",
    }
    data.update(overrides)
    return data


def defect_row(category, severity=None, quantity="10", unit="meters", **extra):
    row = {"category_id": str(category.id), "defect_quantity": quantity, "quantity_unit": unit}
    if severity is not None:
        row["severity_id"] = str(severity.id)
    row.update(extra)
    return row
