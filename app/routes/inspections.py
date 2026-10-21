from __future__ import annotations

from flask import Blueprint, current_app, redirect, render_template, request, url_for

from app.domain.errors import BusinessRuleError, ValidationError
from app.domain.validation import parse_date_value
from app.models import Inspection
from app.routes._helpers import ok, page_number, per_page, query_without_page, warn
from app.services import (
    corrective_action_service,
    defect_service,
    disposition_service,
    inspection_service,
)

bp = Blueprint("inspections", __name__, url_prefix="/inspections")


def _form_page(template: str, *, status: int = 200, **context):
    context.update(inspection_service.form_context())
    return render_template(template, **context), status


@bp.get("/")
def list_view():
    date_from, e1 = parse_date_value(request.args.get("date_from"), label="Start date", required=False)
    date_to, e2 = parse_date_value(request.args.get("date_to"), label="End date", required=False)
    errors = {}
    if e1:
        errors["date_from"], date_from = e1, None
    if e2:
        errors["date_to"], date_to = e2, None
    filters = inspection_service.InspectionFilters(
        q=(request.args.get("q") or "").strip(),
        date_from=date_from,
        date_to=date_to,
        product=(request.args.get("product") or "").strip(),
        batch=(request.args.get("batch") or "").strip(),
        stage=(request.args.get("stage") or "").strip(),
        disposition=(request.args.get("disposition") or "").strip(),
    )
    page = inspection_service.list_inspections(filters, page_number(), per_page())
    return render_template(
        "inspections/list.html",
        page=page,
        filters=filters,
        errors=errors,
        qs=query_without_page(),
        products=inspection_service.distinct_values(Inspection.product_reference),
        batches=inspection_service.distinct_values(Inspection.batch_reference),
        stages=inspection_service.distinct_values(Inspection.production_stage),
        disposition_status=inspection_service.disposition_status,
    )


@bp.route("/new", methods=["GET", "POST"])
def create():
    if request.method == "GET":
        return _form_page("inspections/form.html", inspection=None, form={}, errors={}, rows=[])
    rows = inspection_service.extract_defect_rows(request.form, request.form.getlist)
    try:
        inspection = inspection_service.create_inspection(
            request.form, rows, max_defects=current_app.config["MAX_DEFECTS_PER_FORM"]
        )
    except ValidationError as exc:
        warn("The inspection was not saved. Please correct the highlighted fields.")
        return _form_page(
            "inspections/form.html", status=400, inspection=None, form=request.form, errors=exc.errors, rows=rows
        )
    ok(f"Inspection {inspection.inspection_code} saved.")
    return redirect(url_for("inspections.detail", inspection_id=inspection.id))


@bp.get("/<int:inspection_id>")
def detail(inspection_id: int):
    inspection = inspection_service.get_inspection(inspection_id)
    disposition = disposition_service.get_disposition(inspection_id)
    return render_template(
        "inspections/detail.html",
        inspection=inspection,
        defects=sorted(inspection.defects, key=lambda d: d.id),
        disposition=disposition,
        disposition_state=inspection_service.disposition_status(disposition),
        actions=sorted(inspection.corrective_actions, key=lambda a: a.id),
        dependencies=inspection_service.dependency_counts(inspection_id),
        today=corrective_action_service.today(),
    )


@bp.route("/<int:inspection_id>/edit", methods=["GET", "POST"])
def edit(inspection_id: int):
    inspection = inspection_service.get_inspection(inspection_id)
    if request.method == "GET":
        return _form_page("inspections/form.html", inspection=inspection, form={}, errors={}, rows=[])
    try:
        inspection_service.update_inspection(inspection_id, request.form)
    except ValidationError as exc:
        warn("The changes were not saved. Please correct the highlighted fields.")
        return _form_page(
            "inspections/form.html", status=400, inspection=inspection, form=request.form, errors=exc.errors, rows=[]
        )
    ok("Inspection updated.")
    return redirect(url_for("inspections.detail", inspection_id=inspection_id))


@bp.post("/<int:inspection_id>/delete")
def delete(inspection_id: int):
    try:
        inspection_service.delete_inspection(inspection_id)
    except BusinessRuleError as exc:
        warn(str(exc))
        return redirect(url_for("inspections.detail", inspection_id=inspection_id))
    ok("Inspection deleted.")
    return redirect(url_for("inspections.list_view"))


# ---- disposition ----------------------------------------------------------------------
@bp.route("/<int:inspection_id>/disposition", methods=["GET", "POST"])
def disposition(inspection_id: int):
    inspection = inspection_service.get_inspection(inspection_id)
    record = disposition_service.get_disposition(inspection_id)
    if request.method == "GET":
        return render_template(
            "inspections/disposition.html", inspection=inspection, record=record, form={}, errors={}
        )
    try:
        disposition_service.save_disposition(inspection_id, request.form)
    except ValidationError as exc:
        warn("The disposition was not saved. Please correct the highlighted fields.")
        return (
            render_template(
                "inspections/disposition.html",
                inspection=inspection,
                record=record,
                form=request.form,
                errors=exc.errors,
            ),
            400,
        )
    ok("Disposition saved.")
    return redirect(url_for("inspections.detail", inspection_id=inspection_id))


@bp.post("/<int:inspection_id>/disposition/delete")
def disposition_delete(inspection_id: int):
    disposition_service.delete_disposition(inspection_id)
    ok("Disposition record removed.")
    return redirect(url_for("inspections.detail", inspection_id=inspection_id))


# ---- defects on an existing inspection --------------------------------------------------
@bp.route("/<int:inspection_id>/defects/new", methods=["GET", "POST"])
def add_defect(inspection_id: int):
    inspection = inspection_service.get_inspection(inspection_id)
    ctx = inspection_service.form_context()
    if request.method == "POST":
        try:
            defect_service.add_defect(inspection_id, request.form)
        except ValidationError as exc:
            warn("The defect was not saved. Please correct the highlighted fields.")
            return (
                render_template(
                    "defects/form.html", inspection=inspection, defect=None, form=request.form, errors=exc.errors, **ctx
                ),
                400,
            )
        ok("Defect entry added.")
        return redirect(url_for("inspections.detail", inspection_id=inspection_id))
    return render_template("defects/form.html", inspection=inspection, defect=None, form={}, errors={}, **ctx)
