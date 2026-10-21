"""Blueprint registration."""

from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from app.routes.actions import bp as actions_bp
    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.data import bp as data_bp
    from app.routes.defects import bp as defects_bp
    from app.routes.inspections import bp as inspections_bp
    from app.routes.reports import bp as reports_bp

    for blueprint in (dashboard_bp, inspections_bp, defects_bp, actions_bp, reports_bp, data_bp):
        app.register_blueprint(blueprint)
