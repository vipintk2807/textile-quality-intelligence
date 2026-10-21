"""Corrective actions: records, controlled status transitions and follow-up history."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.domain import workflow
from app.domain.errors import BusinessRuleError, NotFoundError, ValidationError
from app.domain.validation import (
    LIMITS,
    clean_text,
    escape_like,
    parse_date_value,
    parse_optional_id,
)
from app.extensions import db
from app.models import ActionFollowUp, CorrectiveAction, DefectEntry, Inspection
from app.services.pagination import Page, paginate

log = logging.getLogger(__name__)


def today() -> date:
    return date.today()


def _commit() -> None:
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        log.exception("Database error saving corrective action data")
        raise


def get_action(action_id: int) -> CorrectiveAction:
    action = db.session.get(CorrectiveAction, action_id)
    if action is None:
        raise NotFoundError("That corrective action could not be found.")
    return action


def validate_action(data: Mapping[str, str], *, require_inspection: bool = True) -> tuple[dict, dict[str, str]]:
    errors: dict[str, str] = {}
    clean: dict = {}

    if require_inspection:
        inspection_id = parse_optional_id(data.get("inspection_id"))
        inspection = db.session.get(Inspection, inspection_id) if inspection_id else None
        if inspection is None:
            errors["inspection_id"] = "Select an existing inspection."
        else:
            clean["inspection_id"] = inspection.id
            defect_raw = (data.get("defect_entry_id") or "").strip()
            if defect_raw:
                defect_id = parse_optional_id(defect_raw)
                defect = db.session.get(DefectEntry, defect_id) if defect_id else None
                if defect is None or defect.inspection_id != inspection.id:
                    errors["defect_entry_id"] = (
                        "The selected defect record does not belong to that inspection."
                    )
                else:
                    clean["defect_entry_id"] = defect.id
            else:
                clean["defect_entry_id"] = None

    for name, label, limit, required in (
        ("problem_description", "Problem description", LIMITS["long_text"], True),
        ("suspected_cause", "Suspected cause", LIMITS["long_text"], False),
        ("confirmed_root_cause", "Confirmed root cause", LIMITS["long_text"], False),
        ("action_description", "Corrective action description", LIMITS["long_text"], False),
        ("responsible_person", "Responsible person", LIMITS["person"], False),
        ("notes", "Notes", LIMITS["long_text"], False),
    ):
        value, err = clean_text(data.get(name), label=label, max_length=limit, required=required)
        if err:
            errors[name] = err
        else:
            clean[name] = value

    target, err = parse_date_value(data.get("target_date"), label="Target date", required=False)
    if err:
        errors["target_date"] = err
    else:
        clean["target_date"] = target
    return clean, errors


def create_action(data: Mapping[str, str]) -> CorrectiveAction:
    clean, errors = validate_action(data)
    if errors:
        raise ValidationError(errors)
    action = CorrectiveAction(status=workflow.OPEN, **clean)
    db.session.add(action)
    _commit()
    return action


def update_action(action_id: int, data: Mapping[str, str]) -> CorrectiveAction:
    action = get_action(action_id)
    if action.status == workflow.CLOSED:
        raise BusinessRuleError("A closed corrective action cannot be edited.")
    clean, errors = validate_action(data, require_inspection=False)
    if errors:
        raise ValidationError(errors)
    for key, value in clean.items():
        setattr(action, key, value)
    _commit()
    return action


def latest_followup(action_id: int) -> ActionFollowUp | None:
    return db.session.scalar(
        select(ActionFollowUp)
        .where(ActionFollowUp.corrective_action_id == action_id)
        .order_by(ActionFollowUp.follow_up_date.desc(), ActionFollowUp.id.desc())
        .limit(1)
    )


def change_status(action_id: int, target: str, data: Mapping[str, str]) -> CorrectiveAction:
    """Move an action to a new status only if the workflow rules allow it."""
    action = get_action(action_id)
    if target not in workflow.STATUSES:
        raise BusinessRuleError("Unknown status requested.")

    completed_on = action.completed_on
    errors: dict[str, str] = {}
    if target == workflow.COMPLETED:
        completed_on, err = parse_date_value(
            data.get("completed_on"), label="Completion date", required=False
        )
        if err:
            errors["completed_on"] = err

    followup = latest_followup(action_id)
    problems = workflow.check_transition(
        action.status,
        target,
        action_description=action.action_description,
        completed_on=completed_on,
        today=today(),
        latest_followup=(followup.follow_up_date, followup.result) if followup else None,
    )
    if problems:
        errors["status"] = " ".join(problems)
    if errors:
        raise ValidationError(errors)

    action.status = target
    if target == workflow.COMPLETED:
        action.completed_on = completed_on
    elif target in workflow.REOPEN_TARGETS:
        action.completed_on = None
    _commit()
    return action


def add_followup(action_id: int, data: Mapping[str, str]) -> ActionFollowUp:
    """Record an effectiveness assessment (only while the action awaits follow-up)."""
    action = get_action(action_id)
    errors: dict[str, str] = {}
    if action.status != workflow.COMPLETED:
        raise BusinessRuleError(
            "Follow-up assessments can be recorded only while an action is "
            f"'{workflow.status_label(workflow.COMPLETED)}'."
        )

    follow_up_date, err = parse_date_value(data.get("follow_up_date"), label="Follow-up date")
    if err:
        errors["follow_up_date"] = err
    elif follow_up_date > today():
        errors["follow_up_date"] = "The follow-up date cannot be in the future."
    elif action.completed_on and follow_up_date < action.completed_on:
        errors["follow_up_date"] = "The follow-up date cannot be earlier than the completion date."

    result = (data.get("result") or "").strip()
    if result not in workflow.FOLLOWUP_RESULTS:
        errors["result"] = "Select the assessment result."

    observations, err = clean_text(
        data.get("observations"), label="Evidence / observations", max_length=LIMITS["long_text"], required=True
    )
    if err:
        errors["observations"] = err
    recorded_by, err = clean_text(data.get("recorded_by"), label="Recorded by", max_length=LIMITS["person"])
    if err:
        errors["recorded_by"] = err
    if errors:
        raise ValidationError(errors)

    followup = ActionFollowUp(
        corrective_action_id=action_id,
        follow_up_date=follow_up_date,
        result=result,
        observations=observations,
        recorded_by=recorded_by,
    )
    db.session.add(followup)
    _commit()
    return followup


@dataclass
class ActionFilters:
    status: str = ""
    responsible: str = ""
    product: str = ""
    batch: str = ""
    q: str = ""
    overdue_only: bool = False


def list_actions(filters: ActionFilters, page: int, per_page: int) -> Page:
    stmt = (
        select(CorrectiveAction, Inspection)
        .join(Inspection, CorrectiveAction.inspection_id == Inspection.id)
        .order_by(CorrectiveAction.id.desc())
    )
    if filters.status in workflow.STATUSES:
        stmt = stmt.where(CorrectiveAction.status == filters.status)
    if filters.responsible:
        stmt = stmt.where(
            func.lower(func.coalesce(CorrectiveAction.responsible_person, "")) == filters.responsible.lower()
        )
    if filters.product:
        stmt = stmt.where(func.lower(Inspection.product_reference) == filters.product.lower())
    if filters.batch:
        stmt = stmt.where(func.lower(func.coalesce(Inspection.batch_reference, "")) == filters.batch.lower())
    if filters.q:
        pattern = f"%{escape_like(filters.q.lower())}%"
        stmt = stmt.where(
            func.lower(CorrectiveAction.problem_description).like(pattern, escape="\\")
            | func.lower(Inspection.inspection_code).like(pattern, escape="\\")
        )
    if filters.overdue_only:
        stmt = stmt.where(
            CorrectiveAction.target_date.is_not(None),
            CorrectiveAction.target_date < today(),
            CorrectiveAction.status.in_(sorted(workflow.OVERDUE_ELIGIBLE)),
        )
    return paginate(stmt, page, per_page)
