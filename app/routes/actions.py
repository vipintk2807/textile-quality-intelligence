from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, url_for
from sqlalchemy import select

from app.domain import workflow
from app.domain.errors import BusinessRuleError, ValidationError
from app.domain.validation import parse_optional_id
from app.extensions import db
from app.models import CorrectiveAction, DefectEntry, Inspection
from app.routes._helpers import ok, page_number, per_page, query_without_page, warn
from app.services import corrective_action_service as svc
from app.services import inspection_service

bp = Blueprint("actions", __name__, url_prefix="/actions")


def _inspection_options() -> list[Inspection]:
    return list(
        db.session.scalars(
            select(Inspection).order_by(Inspection.inspection_date.desc(), Inspection.id.desc()).limit(500)
        )
    )


def _defect_options(inspection_id: int | None) -> list[DefectEntry]:
    if not inspection_id:
        return []
    return list(db.session.scalars(select(DefectEntry).where(DefectEntry.inspection_id == inspection_id)))


def _form(status: int = 200, *, action=None, form=None, errors=None):
    form = form or {}
    inspection_id = (
        parse_optional_id(form.get("inspection_id"))
        or (action.inspection_id if action else None)
        or parse_optional_id(request.args.get("inspection_id"))
    )
    return (
        render_template(
            "corrective_actions/form.html",
            action=action,
            form=form,
            errors=errors or {},
            inspections=_inspection_options(),
            defects=_defect_options(inspection_id),
            selected_inspection=inspection_id,
            selected_defect=parse_optional_id(form.get("defect_entry_id"))
            or (action.defect_entry_id if action else None)
            or parse_optional_id(request.args.get("defect_entry_id")),
        ),
        status,
    )


@bp.get("/")
def list_view():
    filters = svc.ActionFilters(
        status=(request.args.get("status") or "").strip(),
        responsible=(request.args.get("responsible") or "").strip(),
        product=(request.args.get("product") or "").strip(),
        batch=(request.args.get("batch") or "").strip(),
        q=(request.args.get("q") or "").strip(),
        overdue_only=request.args.get("overdue") == "1",
    )
    page = svc.list_actions(filters, page_number(), per_page())
    return render_template(
        "corrective_actions/list.html",
        page=page,
        filters=filters,
        qs=query_without_page(),
        today=svc.today(),
        is_overdue=workflow.is_overdue,
        products=inspection_service.distinct_values(Inspection.product_reference),
        batches=inspection_service.distinct_values(Inspection.batch_reference),
        responsible_people=inspection_service.distinct_values(CorrectiveAction.responsible_person),
    )


@bp.route("/new", methods=["GET", "POST"])
def create():
    if request.method == "GET":
        return _form()
    try:
        action = svc.create_action(request.form)
    except ValidationError as exc:
        warn("The corrective action was not saved. Please correct the highlighted fields.")
        return _form(400, form=request.form, errors=exc.errors)
    ok("Corrective action recorded.")
    return redirect(url_for("actions.detail", action_id=action.id))


@bp.get("/<int:action_id>")
def detail(action_id: int):
    action = svc.get_action(action_id)
    today = svc.today()
    return render_template(
        "corrective_actions/detail.html",
        action=action,
        inspection=action.inspection,
        followups=sorted(action.follow_ups, key=lambda f: (f.follow_up_date, f.id), reverse=True),
        next_statuses=workflow.permitted_next(action.status),
        overdue=workflow.is_overdue(action.target_date, action.status, today),
        today=today,
        form={},
        errors={},
    )


@bp.route("/<int:action_id>/edit", methods=["GET", "POST"])
def edit(action_id: int):
    action = svc.get_action(action_id)
    if request.method == "GET":
        return _form(action=action)
    try:
        svc.update_action(action_id, request.form)
    except ValidationError as exc:
        warn("The changes were not saved. Please correct the highlighted fields.")
        return _form(400, action=action, form=request.form, errors=exc.errors)
    ok("Corrective action updated.")
    return redirect(url_for("actions.detail", action_id=action_id))


def _detail_with_errors(action_id: int, errors: dict[str, str], section: str):
    action = svc.get_action(action_id)
    today = svc.today()
    return (
        render_template(
            "corrective_actions/detail.html",
            action=action,
            inspection=action.inspection,
            followups=sorted(action.follow_ups, key=lambda f: (f.follow_up_date, f.id), reverse=True),
            next_statuses=workflow.permitted_next(action.status),
            overdue=workflow.is_overdue(action.target_date, action.status, today),
            today=today,
            form=request.form,
            errors=errors,
            error_section=section,
        ),
        400,
    )


@bp.post("/<int:action_id>/status")
def change_status(action_id: int):
    target = (request.form.get("status") or "").strip()
    try:
        action = svc.change_status(action_id, target, request.form)
    except ValidationError as exc:
        warn("The status was not changed. " + " ".join(exc.errors.values()))
        return _detail_with_errors(action_id, exc.errors, "status")
    except BusinessRuleError as exc:
        warn(str(exc))
        return redirect(url_for("actions.detail", action_id=action_id))
    ok(f"Status changed to '{workflow.status_label(action.status)}'.")
    return redirect(url_for("actions.detail", action_id=action_id))


@bp.post("/<int:action_id>/followup")
def add_followup(action_id: int):
    try:
        svc.add_followup(action_id, request.form)
    except ValidationError as exc:
        warn("The follow-up was not saved. Please correct the highlighted fields.")
        return _detail_with_errors(action_id, exc.errors, "followup")
    except BusinessRuleError as exc:
        warn(str(exc))
        return redirect(url_for("actions.detail", action_id=action_id))
    ok("Follow-up assessment recorded. You can now set the action's status to Effective or Not effective.")
    return redirect(url_for("actions.detail", action_id=action_id))
