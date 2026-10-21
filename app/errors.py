"""Safe, user-friendly error pages. Details go to the log, never to the browser."""

from __future__ import annotations

import logging

from flask import Flask, render_template
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import SQLAlchemyError

from app.domain.errors import BusinessRuleError, NotFoundError

log = logging.getLogger(__name__)


def _page(title: str, message: str, status: int):
    return render_template("error.html", title=title, message=message, status=status), status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_error):
        return _page("Page not found", "The page or record you asked for could not be found.", 404)

    @app.errorhandler(NotFoundError)
    def record_not_found(error):
        return _page("Record not found", str(error), 404)

    @app.errorhandler(BusinessRuleError)
    def rule_violation(error):
        return _page("Action not completed", str(error), 400)

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return _page("Action not allowed", "That action is not allowed for this page.", 405)

    @app.errorhandler(413)
    def too_large(_error):
        return _page("Request too large", "The submitted form was too large to process.", 413)

    @app.errorhandler(CSRFError)
    def csrf_failed(error):
        log.warning("CSRF validation failed: %s", error.description)
        return _page(
            "Form expired",
            "The form could not be verified (it may have expired). Go back, reload the page and "
            "submit again. Nothing was saved.",
            400,
        )

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        log.exception("Database error")
        return _page(
            "Database problem",
            "The database could not complete the request. Nothing was changed. If this keeps "
            "happening, check that the database has been created ('flask --app run db upgrade') "
            "and see the Data Management page.",
            500,
        )

    @app.errorhandler(500)
    def server_error(_error):
        return _page(
            "Something went wrong",
            "An unexpected error occurred. Your data was not changed by this request. "
            "Diagnostic details were written to the application log.",
            500,
        )
