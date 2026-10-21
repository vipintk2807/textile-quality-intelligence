"""Small helpers shared by the route modules."""

from __future__ import annotations

from flask import current_app, flash, request

from app.domain.validation import parse_page


def page_number() -> int:
    return parse_page(request.args.get("page"))


def per_page() -> int:
    return int(current_app.config["PAGE_SIZE"])


def ok(message: str) -> None:
    flash(message, "success")


def warn(message: str) -> None:
    flash(message, "error")


def query_without_page() -> dict[str, str]:
    """Current query string minus ``page`` (used to build pagination links)."""
    return {k: v for k, v in request.args.items() if k != "page" and v != ""}
