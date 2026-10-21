from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, url_for

from app.domain.errors import BusinessRuleError, ValidationError
from app.domain.validation import parse_optional_id
from app.routes._helpers import ok, page_number, per_page, query_without_page, warn
from app.services import defect_service, inspection_service

bp = Blueprint("defects", __name__, url_prefix="/defects")


@bp.get("/")
def list_view():
    severity_raw = (request.args.get("severity_id") or "").strip()
    filters = defect_service.DefectFilters(
        category_id=parse_optional_id(request.args.get("category_id")),
        severity_id=-1 if severity_raw == "-1" else parse_optional_id(severity_raw),
        q=(request.args.get("q") or "").strip(),
    )
    page = defect_service.list_defects(filters, page_number(), per_page())
    return render_template(
        "defects/list.html",
        page=page,
        filters=filters,
        qs=query_without_page(),
        categories=defect_service.list_categories(),
        severities=defect_service.list_severities(),
    )


@bp.route("/<int:defect_id>/edit", methods=["GET", "POST"])
def edit(defect_id: int):
    defect = defect_service.get_defect(defect_id)
    ctx = inspection_service.form_context()
    # Keep inactive-but-used reference values selectable when editing.
    ctx["categories"] = defect_service.list_categories()
    ctx["severities"] = defect_service.list_severities()
    if request.method == "POST":
        try:
            defect_service.update_defect(defect_id, request.form)
        except ValidationError as exc:
            warn("The changes were not saved. Please correct the highlighted fields.")
            return (
                render_template(
                    "defects/form.html",
                    inspection=defect.inspection,
                    defect=defect,
                    form=request.form,
                    errors=exc.errors,
                    **ctx,
                ),
                400,
            )
        ok("Defect entry updated.")
        return redirect(url_for("inspections.detail", inspection_id=defect.inspection_id))
    return render_template(
        "defects/form.html", inspection=defect.inspection, defect=defect, form={}, errors={}, **ctx
    )


@bp.post("/<int:defect_id>/delete")
def delete(defect_id: int):
    defect = defect_service.get_defect(defect_id)
    inspection_id = defect.inspection_id
    try:
        defect_service.delete_defect(defect_id)
    except BusinessRuleError as exc:
        warn(str(exc))
    else:
        ok("Defect entry deleted.")
    return redirect(url_for("inspections.detail", inspection_id=inspection_id))


# ---- reference data: categories and severity levels --------------------------------------
def _reference_page(kind: str):
    return {
        "category": dict(
            title="Defect categories",
            items=defect_service.list_categories(),
            create=defect_service.create_category,
            update=defect_service.update_category,
            toggle=defect_service.set_category_active,
            get=defect_service.get_category,
            endpoint="defects.categories",
            sortable=False,
        ),
        "severity": dict(
            title="Severity levels",
            items=defect_service.list_severities(),
            create=defect_service.create_severity,
            update=defect_service.update_severity,
            toggle=defect_service.set_severity_active,
            get=defect_service.get_severity,
            endpoint="defects.severities",
            sortable=True,
        ),
    }[kind]


def _handle_reference(kind: str):
    cfg = _reference_page(kind)
    edit_id = parse_optional_id(request.args.get("edit"))
    editing = None
    if edit_id:
        try:
            editing = cfg["get"](edit_id)
        except Exception:  # NotFoundError -> just show the list
            editing = None
    form, errors, status = {}, {}, 200
    if request.method == "POST":
        action = request.form.get("action", "save")
        try:
            if action == "toggle":
                target_id = parse_optional_id(request.form.get("id"))
                item = cfg["get"](target_id) if target_id else None
                if item is not None:
                    cfg["toggle"](item.id, not item.is_active)
                    ok(f"'{item.name}' is now {'active' if item.is_active else 'inactive'}.")
                return redirect(url_for(cfg["endpoint"]))
            target_id = parse_optional_id(request.form.get("id"))
            if target_id:
                cfg["update"](target_id, request.form)
                ok("Changes saved.")
            else:
                cfg["create"](request.form)
                ok("Added.")
            return redirect(url_for(cfg["endpoint"]))
        except ValidationError as exc:
            errors, form, status = exc.errors, request.form, 400
            warn("Not saved. Please correct the highlighted fields.")
            target_id = parse_optional_id(request.form.get("id"))
            editing = cfg["get"](target_id) if target_id else None
    return (
        render_template(
            "defects/reference.html",
            kind=kind,
            title=cfg["title"],
            items=cfg["items"],
            editing=editing,
            form=form,
            errors=errors,
            endpoint=cfg["endpoint"],
            sortable=cfg["sortable"],
        ),
        status,
    )


@bp.route("/categories", methods=["GET", "POST"])
def categories():
    return _handle_reference("category")


@bp.route("/severities", methods=["GET", "POST"])
def severities():
    return _handle_reference("severity")
