"""Disposition recording (accepted / rework / rejected / pending) with reconciliation."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.domain.disposition import check_disposition
from app.domain.errors import NotFoundError, ValidationError
from app.domain.validation import LIMITS, clean_text, normalise_unit, parse_whole_number
from app.extensions import db
from app.models import DispositionRecord
from app.services.inspection_service import get_inspection

log = logging.getLogger(__name__)

QUANTITY_FIELDS = (
    ("accepted_quantity", "Accepted quantity"),
    ("rework_quantity", "Rework quantity"),
    ("rejected_quantity", "Rejected quantity"),
    ("pending_quantity", "Pending quantity"),
)


def validate_disposition(inspection, data: Mapping[str, str]) -> tuple[dict, dict[str, str]]:
    """Validate the four quantities and reconcile them with the inspected quantity."""
    errors: dict[str, str] = {}
    clean: dict = {}

    for name, label in QUANTITY_FIELDS:
        raw = data.get(name)
        if raw is None or not str(raw).strip():
            errors[name] = f"{label} is required. Enter 0 if there is none."
            continue
        value, err = parse_whole_number(raw, label=label, minimum=0)
        if err:
            errors[name] = err
        else:
            clean[name] = value

    unit_raw = (data.get("quantity_unit") or "").strip()
    if unit_raw:
        unit, err = normalise_unit(unit_raw, label="Unit")
        if err:
            errors["quantity_unit"] = err
        else:
            clean["quantity_unit"] = unit
    else:
        clean["quantity_unit"] = inspection.quantity_unit

    notes, err = clean_text(data.get("notes"), label="Notes", max_length=LIMITS["long_text"])
    if err:
        errors["notes"] = err
    else:
        clean["notes"] = notes

    if not errors:
        problems = check_disposition(
            inspected_quantity=inspection.inspected_quantity,
            inspected_unit=inspection.quantity_unit,
            accepted=clean["accepted_quantity"],
            rework=clean["rework_quantity"],
            rejected=clean["rejected_quantity"],
            pending=clean["pending_quantity"],
            unit=clean["quantity_unit"],
        )
        if problems:
            errors["reconciliation"] = " ".join(problems)
    return clean, errors


def get_disposition(inspection_id: int) -> DispositionRecord | None:
    return db.session.scalar(
        select(DispositionRecord).where(DispositionRecord.inspection_id == inspection_id)
    )


def save_disposition(inspection_id: int, data: Mapping[str, str]) -> DispositionRecord:
    """Create or replace the single disposition record of an inspection (one transaction)."""
    inspection = get_inspection(inspection_id)
    clean, errors = validate_disposition(inspection, data)
    if errors:
        raise ValidationError(errors)

    record = get_disposition(inspection_id)
    if record is None:
        record = DispositionRecord(inspection_id=inspection_id, **clean)
        db.session.add(record)
    else:
        for key, value in clean.items():
            setattr(record, key, value)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        log.exception("Database error saving disposition for inspection %s", inspection_id)
        raise
    return record


def delete_disposition(inspection_id: int) -> None:
    record = get_disposition(inspection_id)
    if record is None:
        raise NotFoundError("There is no disposition record for this inspection.")
    db.session.delete(record)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        log.exception("Database error deleting disposition for inspection %s", inspection_id)
        raise
