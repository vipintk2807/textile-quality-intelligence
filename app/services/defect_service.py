"""Defect entries and the reference data they use (categories, severity levels)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.domain.errors import BusinessRuleError, NotFoundError, ValidationError
from app.domain.validation import (
    LIMITS,
    clean_text,
    escape_like,
    normalise_unit,
    parse_optional_id,
    parse_whole_number,
)
from app.extensions import db
from app.models import CorrectiveAction, DefectCategory, DefectEntry, Inspection, SeverityLevel
from app.services.pagination import Page, paginate

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------------------
# Reference data: categories and severity levels
# --------------------------------------------------------------------------------------
def list_categories(*, active_only: bool = False) -> list[DefectCategory]:
    stmt = select(DefectCategory).order_by(DefectCategory.is_active.desc(), DefectCategory.name_key)
    if active_only:
        stmt = stmt.where(DefectCategory.is_active.is_(True))
    return list(db.session.scalars(stmt))


def list_severities(*, active_only: bool = False) -> list[SeverityLevel]:
    stmt = select(SeverityLevel).order_by(
        SeverityLevel.is_active.desc(), SeverityLevel.sort_order, SeverityLevel.name_key
    )
    if active_only:
        stmt = stmt.where(SeverityLevel.is_active.is_(True))
    return list(db.session.scalars(stmt))


def _validate_reference(data: Mapping[str, str], model, *, current_id: int | None, kind: str):
    errors: dict[str, str] = {}
    name, err = clean_text(data.get("name"), label="Name", max_length=LIMITS["name"], required=True)
    if err:
        errors["name"] = err
    description, err = clean_text(
        data.get("description"), label="Description", max_length=LIMITS["short_text"]
    )
    if err:
        errors["description"] = err
    sort_order = 0
    if model is SeverityLevel:
        sort_order, err = parse_whole_number(
            data.get("sort_order") or "0", label="Display order", minimum=0, maximum=10_000
        )
        if err:
            errors["sort_order"] = err
    if name and not errors.get("name"):
        key = name.lower()
        stmt = select(model.id).where(model.name_key == key)
        if current_id is not None:
            stmt = stmt.where(model.id != current_id)
        if db.session.scalar(stmt) is not None:
            errors["name"] = f"A {kind} named '{name}' already exists (names are not case-sensitive)."
    if errors:
        raise ValidationError(errors)
    return name, name.lower(), description, sort_order


def _commit() -> None:
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        log.warning("Integrity error while saving: %s", exc.orig)
        raise BusinessRuleError(
            "The change could not be saved because it conflicts with existing records."
        ) from exc
    except SQLAlchemyError:
        db.session.rollback()
        log.exception("Database error while saving")
        raise


def create_category(data: Mapping[str, str]) -> DefectCategory:
    name, key, description, _ = _validate_reference(
        data, DefectCategory, current_id=None, kind="defect category"
    )
    category = DefectCategory(name=name, name_key=key, description=description, is_active=True)
    db.session.add(category)
    _commit()
    return category


def update_category(category_id: int, data: Mapping[str, str]) -> DefectCategory:
    category = get_category(category_id)
    name, key, description, _ = _validate_reference(
        data, DefectCategory, current_id=category_id, kind="defect category"
    )
    category.name, category.name_key, category.description = name, key, description
    _commit()
    return category


def set_category_active(category_id: int, active: bool) -> DefectCategory:
    category = get_category(category_id)
    category.is_active = active
    _commit()
    return category


def get_category(category_id: int) -> DefectCategory:
    category = db.session.get(DefectCategory, category_id)
    if category is None:
        raise NotFoundError("That defect category could not be found.")
    return category


def create_severity(data: Mapping[str, str]) -> SeverityLevel:
    name, key, description, order = _validate_reference(
        data, SeverityLevel, current_id=None, kind="severity level"
    )
    severity = SeverityLevel(
        name=name, name_key=key, description=description, sort_order=order, is_active=True
    )
    db.session.add(severity)
    _commit()
    return severity


def update_severity(severity_id: int, data: Mapping[str, str]) -> SeverityLevel:
    severity = get_severity(severity_id)
    name, key, description, order = _validate_reference(
        data, SeverityLevel, current_id=severity_id, kind="severity level"
    )
    severity.name, severity.name_key = name, key
    severity.description, severity.sort_order = description, order
    _commit()
    return severity


def set_severity_active(severity_id: int, active: bool) -> SeverityLevel:
    severity = get_severity(severity_id)
    severity.is_active = active
    _commit()
    return severity


def get_severity(severity_id: int) -> SeverityLevel:
    severity = db.session.get(SeverityLevel, severity_id)
    if severity is None:
        raise NotFoundError("That severity level could not be found.")
    return severity


# Illustrative starter values only - NOT a universal textile-industry taxonomy.
ILLUSTRATIVE_CATEGORIES = (
    ("Hole", "Illustrative example category."),
    ("Stain", "Illustrative example category."),
    ("Shade variation", "Illustrative example category."),
    ("Stitching defect", "Illustrative example category."),
    ("Measurement deviation", "Illustrative example category."),
)
ILLUSTRATIVE_SEVERITIES = (
    ("Minor", "Illustrative label. Define what it means for your deployment.", 1),
    ("Major", "Illustrative label. Define what it means for your deployment.", 2),
    ("Critical", "Illustrative label. Define what it means for your deployment.", 3),
)


def seed_illustrative_reference_data() -> tuple[int, int]:
    """Add illustrative starter categories/severities that do not already exist."""
    added_categories = added_severities = 0
    for name, description in ILLUSTRATIVE_CATEGORIES:
        if db.session.scalar(select(DefectCategory.id).where(DefectCategory.name_key == name.lower())) is None:
            db.session.add(
                DefectCategory(name=name, name_key=name.lower(), description=description, is_active=True)
            )
            added_categories += 1
    for name, description, order in ILLUSTRATIVE_SEVERITIES:
        if db.session.scalar(select(SeverityLevel.id).where(SeverityLevel.name_key == name.lower())) is None:
            db.session.add(
                SeverityLevel(
                    name=name, name_key=name.lower(), description=description,
                    sort_order=order, is_active=True,
                )
            )
            added_severities += 1
    _commit()
    return added_categories, added_severities


# --------------------------------------------------------------------------------------
# Defect entries
# --------------------------------------------------------------------------------------
DEFECT_FIELDS = (
    "category_id",
    "severity_id",
    "defect_quantity",
    "quantity_unit",
    "suspected_cause",
    "observations",
)


def is_blank_row(raw: Mapping[str, str]) -> bool:
    """A defect row where nothing was entered is ignored (an untouched 'Add defect' section)."""
    return not any((raw.get(name) or "").strip() for name in DEFECT_FIELDS)


def validate_defect_row(
    raw: Mapping[str, str],
    *,
    inspection_unit: str | None,
    prefix: str = "",
    existing: DefectEntry | None = None,
) -> tuple[dict, dict[str, str]]:
    """Validate one defect entry. Error keys are ``prefix + field name``."""
    errors: dict[str, str] = {}
    clean: dict = {}

    category_id = parse_optional_id(raw.get("category_id"))
    if category_id is None:
        errors[prefix + "category_id"] = "Select a defect category."
    else:
        category = db.session.get(DefectCategory, category_id)
        keeps_current = existing is not None and existing.category_id == category_id
        if category is None or not (category.is_active or keeps_current):
            errors[prefix + "category_id"] = "The selected defect category is not available."
        else:
            clean["category_id"] = category_id

    severity_raw = (raw.get("severity_id") or "").strip()
    if severity_raw:
        severity_id = parse_optional_id(severity_raw)
        severity = db.session.get(SeverityLevel, severity_id) if severity_id else None
        keeps_current = existing is not None and existing.severity_id == severity_id
        if severity is None or not (severity.is_active or keeps_current):
            errors[prefix + "severity_id"] = "The selected severity level is not available."
        else:
            clean["severity_id"] = severity_id
    else:
        clean["severity_id"] = None  # unclassified: shown as "Not classified", never a default level

    quantity, err = parse_whole_number(raw.get("defect_quantity"), label="Defect quantity")
    if err:
        errors[prefix + "defect_quantity"] = err
    else:
        clean["defect_quantity"] = quantity

    unit_raw = (raw.get("quantity_unit") or "").strip()
    if unit_raw:
        unit, err = normalise_unit(unit_raw, label="Defect unit")
        if err:
            errors[prefix + "quantity_unit"] = err
        elif inspection_unit and unit != inspection_unit:
            errors[prefix + "quantity_unit"] = (
                f"The defect unit must match the inspection unit ('{inspection_unit}')."
            )
        else:
            clean["quantity_unit"] = unit
    elif inspection_unit:
        clean["quantity_unit"] = inspection_unit
    else:
        errors[prefix + "quantity_unit"] = "Defect unit is required."

    for name, label, limit in (
        ("suspected_cause", "Suspected cause", LIMITS["long_text"]),
        ("observations", "Observations", LIMITS["long_text"]),
    ):
        value, err = clean_text(raw.get(name), label=label, max_length=limit)
        if err:
            errors[prefix + name] = err
        else:
            clean[name] = value
    return clean, errors


def get_defect(defect_id: int) -> DefectEntry:
    defect = db.session.get(DefectEntry, defect_id)
    if defect is None:
        raise NotFoundError("That defect record could not be found.")
    return defect


def add_defect(inspection_id: int, raw: Mapping[str, str]) -> DefectEntry:
    inspection = db.session.get(Inspection, inspection_id)
    if inspection is None:
        raise NotFoundError("That inspection could not be found.")
    clean, errors = validate_defect_row(raw, inspection_unit=inspection.quantity_unit)
    if errors:
        raise ValidationError(errors)
    defect = DefectEntry(inspection_id=inspection.id, **clean)
    db.session.add(defect)
    _commit()
    return defect


def update_defect(defect_id: int, raw: Mapping[str, str]) -> DefectEntry:
    defect = get_defect(defect_id)
    clean, errors = validate_defect_row(
        raw, inspection_unit=defect.inspection.quantity_unit, existing=defect
    )
    if errors:
        raise ValidationError(errors)
    for key, value in clean.items():
        setattr(defect, key, value)
    _commit()
    return defect


def delete_defect(defect_id: int) -> None:
    """Delete a saved defect entry unless a corrective action refers to it."""
    defect = get_defect(defect_id)
    linked = db.session.scalar(
        select(func.count()).select_from(CorrectiveAction).where(
            CorrectiveAction.defect_entry_id == defect_id
        )
    )
    if linked:
        raise BusinessRuleError(
            f"This defect record is referenced by {linked} corrective action(s) and cannot be "
            "deleted. Close or re-link those actions first."
        )
    db.session.delete(defect)
    _commit()


@dataclass
class DefectFilters:
    category_id: int | None = None
    severity_id: int | None = None  # -1 means "not classified"
    q: str = ""


def list_defects(filters: DefectFilters, page: int, per_page: int) -> Page:
    stmt = (
        select(DefectEntry, Inspection, DefectCategory, SeverityLevel)
        .join(Inspection, DefectEntry.inspection_id == Inspection.id)
        .join(DefectCategory, DefectEntry.category_id == DefectCategory.id)
        .outerjoin(SeverityLevel, DefectEntry.severity_id == SeverityLevel.id)
        .order_by(Inspection.inspection_date.desc(), DefectEntry.id.desc())
    )
    if filters.category_id:
        stmt = stmt.where(DefectEntry.category_id == filters.category_id)
    if filters.severity_id == -1:
        stmt = stmt.where(DefectEntry.severity_id.is_(None))
    elif filters.severity_id:
        stmt = stmt.where(DefectEntry.severity_id == filters.severity_id)
    if filters.q:
        pattern = f"%{escape_like(filters.q.lower())}%"
        stmt = stmt.where(
            func.lower(Inspection.inspection_code).like(pattern, escape="\\")
            | func.lower(Inspection.product_reference).like(pattern, escape="\\")
            | func.lower(func.coalesce(Inspection.batch_reference, "")).like(pattern, escape="\\")
        )
    return paginate(stmt, page, per_page)
