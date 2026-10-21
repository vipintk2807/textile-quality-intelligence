"""Inspection management: create, read, update, search and (restricted) delete."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.domain.disposition import (  # noqa: F401  (re-exported for routes and reports)
    DISP_NOT_RECORDED,
    DISP_PENDING,
    DISP_RESOLVED,
    DISPOSITION_STATUS_LABELS,
)
from app.domain.errors import BusinessRuleError, NotFoundError, ValidationError
from app.domain.validation import (
    LIMITS,
    clean_text,
    escape_like,
    normalise_unit,
    parse_date_value,
    parse_whole_number,
)
from app.extensions import db
from app.models import CorrectiveAction, DefectEntry, DispositionRecord, Inspection
from app.services import defect_service
from app.services.pagination import Page, paginate

log = logging.getLogger(__name__)

UNIT_SUGGESTIONS = ("pieces", "meters", "yards", "kg")

_ROW_KEY = re.compile(r"^defect-(\d+)-(.+)$")


def disposition_status(record: DispositionRecord | None) -> str:
    """A missing record is *not* treated as 'all accepted'."""
    if record is None:
        return DISP_NOT_RECORDED
    return DISP_PENDING if record.pending_quantity > 0 else DISP_RESOLVED


def extract_defect_rows(form: Mapping[str, str], getlist) -> list[tuple[int, dict[str, str]]]:
    """Collect ``defect-<n>-<field>`` form values into ordered ``(n, row)`` pairs."""
    indices: set[int] = set()
    for key in form.keys():
        match = _ROW_KEY.match(key)
        if match:
            indices.add(int(match.group(1)))
    rows = []
    for index in sorted(indices):
        row = {name: (getlist(f"defect-{index}-{name}") or [""])[0] for name in defect_service.DEFECT_FIELDS}
        rows.append((index, row))
    return rows


# --------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------
def validate_inspection(data: Mapping[str, str]) -> tuple[dict, dict[str, str]]:
    errors: dict[str, str] = {}
    clean: dict = {}

    value, err = parse_date_value(data.get("inspection_date"), label="Inspection date")
    if err:
        errors["inspection_date"] = err
    else:
        clean["inspection_date"] = value

    for name, label, limit, required in (
        ("product_reference", "Product or item reference", LIMITS["reference"], True),
        ("batch_reference", "Batch or lot reference", LIMITS["reference"], False),
        ("production_stage", "Production stage", LIMITS["label"], False),
        ("inspection_type", "Inspection type", LIMITS["label"], False),
        ("inspector_name", "Inspector", LIMITS["person"], False),
        ("notes", "Inspection notes", LIMITS["long_text"], False),
    ):
        value, err = clean_text(data.get(name), label=label, max_length=limit, required=required)
        if err:
            errors[name] = err
        else:
            clean[name] = value

    quantity, err = parse_whole_number(data.get("inspected_quantity"), label="Inspected quantity")
    if err:
        errors["inspected_quantity"] = err
    else:
        clean["inspected_quantity"] = quantity

    unit, err = normalise_unit(data.get("quantity_unit"), label="Unit of measure")
    if err:
        errors["quantity_unit"] = err
    else:
        clean["quantity_unit"] = unit
    return clean, errors


def generate_inspection_code(inspection_date: date) -> str:
    """Next code for the inspection date, e.g. INS-20261018-0001."""
    prefix = f"INS-{inspection_date:%Y%m%d}-"
    last = db.session.scalar(
        select(func.max(Inspection.inspection_code)).where(
            Inspection.inspection_code.like(f"{escape_like(prefix)}%", escape="\\")
        )
    )
    number = int(last[len(prefix):]) + 1 if last else 1
    return f"{prefix}{number:04d}"


# --------------------------------------------------------------------------------------
# Create / read / update / delete
# --------------------------------------------------------------------------------------
def create_inspection(
    data: Mapping[str, str],
    defect_rows: Sequence[tuple[int, Mapping[str, str]]] = (),
    *,
    max_defects: int = 50,
) -> Inspection:
    """Create an inspection and its defect entries in one transaction (all or nothing)."""
    clean, errors = validate_inspection(data)

    rows = [(i, r) for i, r in defect_rows if not defect_service.is_blank_row(r)]
    if len(rows) > max_defects:
        errors["defects"] = f"A single inspection form can contain at most {max_defects} defect entries."
        rows = rows[:max_defects]

    clean_rows: list[dict] = []
    for index, raw in rows:
        row_clean, row_errors = defect_service.validate_defect_row(
            raw, inspection_unit=clean.get("quantity_unit"), prefix=f"defect-{index}-"
        )
        errors.update(row_errors)
        clean_rows.append(row_clean)
    if errors:
        raise ValidationError(errors)

    for attempt in range(5):
        code = generate_inspection_code(clean["inspection_date"])
        inspection = Inspection(inspection_code=code, **clean)
        inspection.defects = [DefectEntry(**row) for row in clean_rows]
        db.session.add(inspection)
        try:
            db.session.commit()
            return inspection
        except IntegrityError as exc:
            db.session.rollback()
            taken = db.session.scalar(
                select(func.count()).select_from(Inspection).where(Inspection.inspection_code == code)
            )
            if taken and attempt < 4:
                log.info("Inspection code %s was taken concurrently; retrying", code)
                continue
            log.warning("Integrity error creating inspection: %s", exc.orig)
            raise BusinessRuleError(
                "The inspection could not be saved because it conflicts with existing records."
            ) from exc
        except SQLAlchemyError:
            db.session.rollback()
            log.exception("Database error creating inspection")
            raise
    raise BusinessRuleError("A unique inspection code could not be generated. Please try again.")


def get_inspection(inspection_id: int) -> Inspection:
    inspection = db.session.get(Inspection, inspection_id)
    if inspection is None:
        raise NotFoundError("That inspection could not be found.")
    return inspection


def update_inspection(inspection_id: int, data: Mapping[str, str]) -> Inspection:
    inspection = get_inspection(inspection_id)
    clean, errors = validate_inspection(data)
    if errors:
        raise ValidationError(errors)

    record = inspection.disposition
    if record is not None and (
        clean["inspected_quantity"] != inspection.inspected_quantity
        or clean["quantity_unit"] != inspection.quantity_unit
    ):
        if clean["quantity_unit"] != record.quantity_unit or clean["inspected_quantity"] != record.total:
            raise ValidationError(
                {
                    "inspected_quantity": (
                        f"A disposition totalling {record.total:,} {record.quantity_unit} is recorded. "
                        "The inspected quantity and unit must stay consistent with it. Remove the "
                        "disposition record first, change the quantity, then record the disposition again."
                    )
                }
            )
    for key, value in clean.items():
        setattr(inspection, key, value)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        log.exception("Database error updating inspection %s", inspection_id)
        raise
    return inspection


def dependency_counts(inspection_id: int) -> dict[str, int]:
    def count(model, column) -> int:
        return int(db.session.scalar(select(func.count()).select_from(model).where(column == inspection_id)) or 0)

    return {
        "defect entries": count(DefectEntry, DefectEntry.inspection_id),
        "disposition records": count(DispositionRecord, DispositionRecord.inspection_id),
        "corrective actions": count(CorrectiveAction, CorrectiveAction.inspection_id),
    }


def delete_inspection(inspection_id: int) -> None:
    """Delete only an inspection with no dependent history (for example one entered in error)."""
    inspection = get_inspection(inspection_id)
    blockers = {name: n for name, n in dependency_counts(inspection_id).items() if n}
    if blockers:
        detail = ", ".join(f"{n} {name}" for name, n in blockers.items())
        raise BusinessRuleError(
            f"{inspection.inspection_code} cannot be deleted because it has related records "
            f"({detail}). Remove or resolve them first so quality history is not lost."
        )
    db.session.delete(inspection)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        log.exception("Database error deleting inspection %s", inspection_id)
        raise


# --------------------------------------------------------------------------------------
# Listing and search
# --------------------------------------------------------------------------------------
@dataclass
class InspectionFilters:
    q: str = ""
    date_from: date | None = None
    date_to: date | None = None
    product: str = ""
    batch: str = ""
    stage: str = ""
    disposition: str = ""

    @property
    def active(self) -> bool:
        return any(
            [self.q, self.date_from, self.date_to, self.product, self.batch, self.stage, self.disposition]
        )


def list_inspections(filters: InspectionFilters, page: int, per_page: int) -> Page:
    """Inspections with their defect-entry count and disposition record (outer joined)."""
    defect_counts = (
        select(DefectEntry.inspection_id.label("iid"), func.count(DefectEntry.id).label("n"))
        .group_by(DefectEntry.inspection_id)
        .subquery()
    )
    stmt = (
        select(Inspection, func.coalesce(defect_counts.c.n, 0), DispositionRecord)
        .outerjoin(defect_counts, defect_counts.c.iid == Inspection.id)
        .outerjoin(DispositionRecord, DispositionRecord.inspection_id == Inspection.id)
        .order_by(Inspection.inspection_date.desc(), Inspection.id.desc())
    )
    if filters.q:
        pattern = f"%{escape_like(filters.q.lower())}%"
        stmt = stmt.where(
            func.lower(Inspection.inspection_code).like(pattern, escape="\\")
            | func.lower(Inspection.product_reference).like(pattern, escape="\\")
            | func.lower(func.coalesce(Inspection.batch_reference, "")).like(pattern, escape="\\")
        )
    if filters.date_from:
        stmt = stmt.where(Inspection.inspection_date >= filters.date_from)
    if filters.date_to:
        stmt = stmt.where(Inspection.inspection_date <= filters.date_to)
    if filters.product:
        stmt = stmt.where(func.lower(Inspection.product_reference) == filters.product.lower())
    if filters.batch:
        stmt = stmt.where(func.lower(func.coalesce(Inspection.batch_reference, "")) == filters.batch.lower())
    if filters.stage:
        stage = filters.stage.lower()
        stmt = stmt.where(
            (func.lower(func.coalesce(Inspection.production_stage, "")) == stage)
            | (func.lower(func.coalesce(Inspection.inspection_type, "")) == stage)
        )
    if filters.disposition == DISP_NOT_RECORDED:
        stmt = stmt.where(DispositionRecord.id.is_(None))
    elif filters.disposition == DISP_PENDING:
        stmt = stmt.where(DispositionRecord.pending_quantity > 0)
    elif filters.disposition == DISP_RESOLVED:
        stmt = stmt.where(DispositionRecord.id.is_not(None), DispositionRecord.pending_quantity == 0)
    return paginate(stmt, page, per_page)


def recent_inspections(limit: int = 10) -> list:
    return list_inspections(InspectionFilters(), 1, limit).items


def distinct_values(column) -> list[str]:
    """Distinct non-empty values of an inspection column, used for form suggestions."""
    rows = db.session.scalars(select(column).where(column.is_not(None)).distinct().order_by(column))
    return [r for r in rows if r]


def form_context() -> dict:
    """Reference data and suggestions needed to render inspection/defect forms."""
    return {
        "categories": defect_service.list_categories(active_only=True),
        "severities": defect_service.list_severities(active_only=True),
        "unit_suggestions": UNIT_SUGGESTIONS,
        "stage_suggestions": sorted(
            set(distinct_values(Inspection.production_stage)) | set(distinct_values(Inspection.inspection_type))
        ),
    }
