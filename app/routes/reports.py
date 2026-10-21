from __future__ import annotations

from flask import Blueprint, render_template, request

from app.domain.metrics import INTERVALS
from app.models import Inspection
from app.services import defect_service, inspection_service
from app.services import reporting_service as rs

bp = Blueprint("reports", __name__, url_prefix="/reports")

VIEWS = (
    ("summary", "Inspection summary"),
    ("defects", "Defect analysis"),
    ("disposition", "Disposition"),
    ("trend", "Trend"),
    ("actions", "Corrective actions"),
)


@bp.get("/")
def index():
    view = request.args.get("view", "summary")
    if view not in dict(VIEWS):
        view = "summary"
    filters, errors = rs.parse_report_filters(request.args)
    interval = request.args.get("interval", "month")
    if interval not in INTERVALS:
        interval = "month"

    data = None
    if not errors:
        if view == "summary":
            data = rs.inspection_summary(filters)
        elif view == "defects":
            data = rs.defect_analysis(filters)
        elif view == "disposition":
            data = rs.disposition_report(filters)
        elif view == "trend":
            data = rs.trend_report(filters, interval)
        else:
            data = rs.corrective_action_report(filters)
    return render_template(
        "reports/index.html",
        views=VIEWS,
        view=view,
        interval=interval,
        intervals=INTERVALS,
        data=data,
        filters=filters,
        errors=errors,
        form=request.args,
        categories=defect_service.list_categories(),
        severities=defect_service.list_severities(),
        products=inspection_service.distinct_values(Inspection.product_reference),
        batches=inspection_service.distinct_values(Inspection.batch_reference),
        stages=inspection_service.distinct_values(Inspection.production_stage),
    )
