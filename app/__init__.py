"""Textile Quality Intelligence application package.

Heavy imports (Flask extensions, models) happen inside ``create_app`` so that the pure
business rules in ``app.domain`` can be imported and unit tested on their own.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


def create_app(config_overrides: dict | None = None) -> Flask:
    """Application factory."""
    from flask import Flask

    from app import cli, errors, template_helpers
    from app.config import load_config
    from app.extensions import csrf, db, migrate
    from app.routes import register_blueprints

    app = Flask(__name__, instance_path=str(Path(__file__).resolve().parent.parent / "instance"))
    app.config.update(load_config((config_overrides or {}).get("TQI_ENV")))
    if config_overrides:
        app.config.update(config_overrides)

    logging.basicConfig(
        level=getattr(logging, str(app.config["LOG_LEVEL"]), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db.init_app(app)
    migrate.init_app(app, db, directory=str(Path(app.root_path).parent / "migrations"))
    csrf.init_app(app)

    from app import models  # noqa: F401  (registers tables with SQLAlchemy metadata)

    register_blueprints(app)
    errors.register_error_handlers(app)
    template_helpers.register(app)
    cli.register(app)

    if not app.config["TESTING"] and not Path(app.config["DATABASE_PATH"]).exists():
        app.logger.warning(
            "Database file not found. Run 'flask --app run db upgrade' to create the schema."
        )
    return app
