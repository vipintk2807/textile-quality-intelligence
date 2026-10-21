from __future__ import annotations

from flask import Blueprint, render_template, request

from app.services import inspection_service, reporting_service

bp = Blueprint("dashboard", __name__)


@bp.get("/")
def index():
    if request.args.get("date_from") or request.args.get("date_to"):
        filters, errors = reporting_service.parse_report_filters(request.args)
    else:
        start, end = reporting_service.default_dashboard_period()
        filters, errors = reporting_service.ReportFilters(date_from=start, date_to=end), {}
    summary = reporting_service.dashboard_summary(filters)
    return render_template(
        "dashboard.html",
        summary=summary,
        filters=filters,
        errors=errors,
        recent=inspection_service.recent_inspections(8),
    )
