"""Jinja filters and template context shared by every page."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from flask import Flask

from app.domain import workflow
from app.domain.metrics import NOT_APPLICABLE
from app.domain.validation import LIMITS

NAV_ITEMS = (
    ("dashboard.index", "Dashboard", "dashboard"),
    ("inspections.list_view", "Inspections", "inspections"),
    ("defects.list_view", "Defects", "defects"),
    ("actions.list_view", "Corrective Actions", "actions"),
    ("reports.index", "Reports", "reports"),
    ("data.index", "Data Management", "data"),
)


def fmt_date(value: date | datetime | None) -> str:
    return "-" if value is None else value.strftime("%Y-%m-%d")


def fmt_datetime(value: datetime | None) -> str:
    return "-" if value is None else value.strftime("%Y-%m-%d %H:%M") + " UTC"


def fmt_qty(value: int | None) -> str:
    return "-" if value is None else f"{value:,}"


def fmt_rate(value: Decimal | None) -> str:
    return NOT_APPLICABLE if value is None else f"{value}%"


def register(app: Flask) -> None:
    app.add_template_filter(fmt_date, "fmt_date")
    app.add_template_filter(fmt_datetime, "fmt_datetime")
    app.add_template_filter(fmt_qty, "qty")
    app.add_template_filter(fmt_rate, "rate")
    app.add_template_filter(workflow.status_label, "status_label")

    from app.domain.disposition import DISPOSITION_STATUS_LABELS as _labels

    # A global (not a context variable) so imported macros can use it too.
    app.add_template_global(_labels, "disposition_labels")

    @app.context_processor
    def inject_globals() -> dict:
        from flask import request

        section = (request.blueprint or "") if request else ""
        return {
            "nav_items": NAV_ITEMS,
            "current_section": section,
            "limits": LIMITS,
            "action_statuses": workflow.STATUSES,
            "action_status_labels": workflow.STATUS_LABELS,
            "followup_labels": workflow.FOLLOWUP_LABELS,
            "today_iso": date.today().isoformat(),
            "NOT_APPLICABLE": NOT_APPLICABLE,
        }
