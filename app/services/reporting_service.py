"""Reporting calculations.

Definitions (all derived from stored records, nothing is hard-coded):

* Inspection count       - number of distinct inspections matching the filters.
* Inspected quantity     - sum of inspected quantities, always grouped by unit.
* Defect entry count     - number of defect entries matching the filters.
* Defect quantity        - sum of defect quantities, always grouped by the defect unit.
                           It is NOT a count of unique defective products.
* Rework / rejection rate - rework (or rejected) quantity divided by the inspected quantity
                           of the inspections that HAVE a disposition record, per unit,
                           x 100. Pending quantity stays in the denominator. Inspections
                           with no disposition record are reported separately and never
                           counted as zero rework or zero rejection. A zero denominator
                           gives "Not applicable".

Inspection-level and defect-level figures come from separate queries so that one-to-many
joins can never multiply inspected quantities.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select

from app.domain import workflow
from app.domain.metrics import INTERVALS, period_key, period_label, rate_percent
from app.domain.validation import parse_date_value, parse_optional_id
from app.extensions import db
from app.models import (
    CorrectiveAction,
    DefectCategory,
    DefectEntry,
    DispositionRecord,
    Inspection,
    SeverityLevel,
)
from app.services.inspection_service import DISP_NOT_RECORDED, DISP_PENDING, DISP_RESOLVED

NOT_CLASSIFIED = "Not classified"
NOT_RECORDED = "Not recorded"
DEFAULT_DASHBOARD_DAYS = 30


@dataclass
class ReportFilters:
    date_from: date | None = None
    date_to: date | None = None  # inclusive
    product: str = ""
    batch: str = ""
    stage: str = ""
    category_id: int | None = None
    severity_id: int | None = None  # -1 = defects without a severity
    disposition: str = ""
    labels: dict[str, str] = field(default_factory=dict, repr=False)

    def describe(self) -> list[str]:
        """Human-readable list of the active filters (shown on every report)."""
        if self.date_from and self.date_to:
            period = f"Inspection date {self.date_from.isoformat()} to {self.date_to.isoformat()} (inclusive)"
        elif self.date_from:
            period = f"Inspection date from {self.date_from.isoformat()}"
        elif self.date_to:
            period = f"Inspection date up to {self.date_to.isoformat()}"
        else:
            period = "All inspection dates"
        parts = [period]
        if self.product:
            parts.append(f"Product = {self.product}")
        if self.batch:
            parts.append(f"Batch = {self.batch}")
        if self.stage:
            parts.append(f"Stage/type = {self.stage}")
        if self.category_id:
            parts.append(f"Defect category = {self.labels.get('category', self.category_id)}")
        if self.severity_id:
            parts.append(f"Severity = {self.labels.get('severity', self.severity_id)}")
        if self.disposition:
            parts.append(f"Disposition = {self.labels.get('disposition', self.disposition)}")
        return parts


def parse_report_filters(args: Mapping[str, str]) -> tuple[ReportFilters, dict[str, str]]:
    """Parse report filters from the query string, reporting invalid values."""
    errors: dict[str, str] = {}
    date_from, err = parse_date_value(args.get("date_from"), label="Start date", required=False)
    if err:
        errors["date_from"] = err
    date_to, err = parse_date_value(args.get("date_to"), label="End date", required=False)
    if err:
        errors["date_to"] = err
    if date_from and date_to and date_from > date_to:
        errors["date_to"] = "The start date must not be after the end date."

    severity_raw = (args.get("severity_id") or "").strip()
    severity_id = -1 if severity_raw == "-1" else parse_optional_id(severity_raw)
    disposition = (args.get("disposition") or "").strip()
    if disposition not in (DISP_NOT_RECORDED, DISP_PENDING, DISP_RESOLVED):
        disposition = ""

    filters = ReportFilters(
        date_from=None if "date_from" in errors else date_from,
        date_to=None if "date_to" in errors else date_to,
        product=(args.get("product") or "").strip(),
        batch=(args.get("batch") or "").strip(),
        stage=(args.get("stage") or "").strip(),
        category_id=parse_optional_id(args.get("category_id")),
        severity_id=severity_id,
        disposition=disposition,
    )
    if filters.category_id:
        category = db.session.get(DefectCategory, filters.category_id)
        filters.labels["category"] = category.name if category else f"#{filters.category_id}"
    if filters.severity_id == -1:
        filters.labels["severity"] = NOT_CLASSIFIED
    elif filters.severity_id:
        severity = db.session.get(SeverityLevel, filters.severity_id)
        filters.labels["severity"] = severity.name if severity else f"#{filters.severity_id}"
    if disposition:
        from app.services.inspection_service import DISPOSITION_STATUS_LABELS

        filters.labels["disposition"] = DISPOSITION_STATUS_LABELS[disposition]
    return filters, errors


# --------------------------------------------------------------------------------------
# Filter conditions
# --------------------------------------------------------------------------------------
def _inspection_conditions(f: ReportFilters) -> list:
    conditions = []
    if f.date_from:
        conditions.append(Inspection.inspection_date >= f.date_from)
    if f.date_to:
        conditions.append(Inspection.inspection_date <= f.date_to)
    if f.product:
        conditions.append(func.lower(Inspection.product_reference) == f.product.lower())
    if f.batch:
        conditions.append(func.lower(func.coalesce(Inspection.batch_reference, "")) == f.batch.lower())
    if f.stage:
        stage = f.stage.lower()
        conditions.append(
            (func.lower(func.coalesce(Inspection.production_stage, "")) == stage)
            | (func.lower(func.coalesce(Inspection.inspection_type, "")) == stage)
        )
    # Correlate ONLY to Inspection; otherwise SQLAlchemy would also correlate DispositionRecord
    # away when the enclosing query already selects from it, leaving the subquery without FROM.
    has_disposition = (
        select(DispositionRecord.id)
        .where(DispositionRecord.inspection_id == Inspection.id)
        .correlate(Inspection)
    )
    if f.disposition == DISP_NOT_RECORDED:
        conditions.append(~has_disposition.exists())
    elif f.disposition == DISP_PENDING:
        conditions.append(has_disposition.where(DispositionRecord.pending_quantity > 0).exists())
    elif f.disposition == DISP_RESOLVED:
        conditions.append(has_disposition.where(DispositionRecord.pending_quantity == 0).exists())

    defect_conditions = _defect_conditions(f)
    if defect_conditions:
        # EXISTS-style membership: never joins, so inspection totals cannot be multiplied.
        conditions.append(Inspection.id.in_(select(DefectEntry.inspection_id).where(*defect_conditions).correlate(None)))
    return conditions


def _defect_conditions(f: ReportFilters) -> list:
    conditions = []
    if f.category_id:
        conditions.append(DefectEntry.category_id == f.category_id)
    if f.severity_id == -1:
        conditions.append(DefectEntry.severity_id.is_(None))
    elif f.severity_id:
        conditions.append(DefectEntry.severity_id == f.severity_id)
    return conditions


def _int(value) -> int:
    return int(value or 0)


# --------------------------------------------------------------------------------------
# Inspection summary
# --------------------------------------------------------------------------------------
def inspection_summary(f: ReportFilters) -> dict:
    conds = _inspection_conditions(f)
    by_unit = db.session.execute(
        select(
            Inspection.quantity_unit,
            func.count(Inspection.id),
            func.sum(Inspection.inspected_quantity),
        )
        .where(*conds)
        .group_by(Inspection.quantity_unit)
        .order_by(Inspection.quantity_unit)
    ).all()
    by_product = db.session.execute(
        select(
            Inspection.product_reference,
            Inspection.quantity_unit,
            func.count(Inspection.id),
            func.sum(Inspection.inspected_quantity),
        )
        .where(*conds)
        .group_by(Inspection.product_reference, Inspection.quantity_unit)
        .order_by(Inspection.product_reference, Inspection.quantity_unit)
    ).all()
    stage_label = func.coalesce(Inspection.production_stage, Inspection.inspection_type, NOT_RECORDED)
    by_stage = db.session.execute(
        select(
            stage_label,
            Inspection.quantity_unit,
            func.count(Inspection.id),
            func.sum(Inspection.inspected_quantity),
        )
        .where(*conds)
        .group_by(stage_label, Inspection.quantity_unit)
        .order_by(stage_label, Inspection.quantity_unit)
    ).all()
    return {
        "total_inspections": sum(_int(r[1]) for r in by_unit),
        "by_unit": [{"unit": r[0], "inspections": _int(r[1]), "quantity": _int(r[2])} for r in by_unit],
        "by_product": [
            {"label": r[0], "unit": r[1], "inspections": _int(r[2]), "quantity": _int(r[3])}
            for r in by_product
        ],
        "by_stage": [
            {"label": r[0], "unit": r[1], "inspections": _int(r[2]), "quantity": _int(r[3])}
            for r in by_stage
        ],
    }


# --------------------------------------------------------------------------------------
# Defect analysis
# --------------------------------------------------------------------------------------
def _defect_select(f: ReportFilters, *columns):
    """SELECT over defect entries joined (many-to-one) to their inspection, with all filters."""
    return (
        select(*columns)
        .select_from(DefectEntry)
        .join(Inspection, DefectEntry.inspection_id == Inspection.id)
        .where(*_inspection_conditions(f), *_defect_conditions(f))
    )


def defect_analysis(f: ReportFilters) -> dict:
    qty = func.sum(DefectEntry.defect_quantity)
    count = func.count(DefectEntry.id)
    entries = db.session.scalar(_defect_select(f, count))
    inspections_with_defects = db.session.scalar(
        _defect_select(f, func.count(func.distinct(DefectEntry.inspection_id)))
    )
    by_unit = db.session.execute(
        _defect_select(f, DefectEntry.quantity_unit, count, qty)
        .group_by(DefectEntry.quantity_unit)
        .order_by(DefectEntry.quantity_unit)
    ).all()
    by_category = db.session.execute(
        _defect_select(f, DefectCategory.name, DefectEntry.quantity_unit, count, qty)
        .join(DefectCategory, DefectEntry.category_id == DefectCategory.id)
        .group_by(DefectCategory.id, DefectCategory.name, DefectEntry.quantity_unit)
        .order_by(count.desc(), DefectCategory.name, DefectEntry.quantity_unit)
    ).all()
    severity_name = func.coalesce(SeverityLevel.name, NOT_CLASSIFIED)
    by_severity = db.session.execute(
        _defect_select(f, severity_name, DefectEntry.quantity_unit, count, qty)
        .outerjoin(SeverityLevel, DefectEntry.severity_id == SeverityLevel.id)
        .group_by(SeverityLevel.id, severity_name, DefectEntry.quantity_unit)
        .order_by(
            func.coalesce(SeverityLevel.sort_order, 1_000_000), severity_name, DefectEntry.quantity_unit
        )
    ).all()
    by_product = db.session.execute(
        _defect_select(f, Inspection.product_reference, DefectEntry.quantity_unit, count, qty)
        .group_by(Inspection.product_reference, DefectEntry.quantity_unit)
        .order_by(count.desc(), Inspection.product_reference)
    ).all()

    def rows(result):
        return [
            {"label": r[0], "unit": r[1], "entries": _int(r[2]), "quantity": _int(r[3])}
            for r in result
        ]

    return {
        "entries": _int(entries),
        "inspections_with_defects": _int(inspections_with_defects),
        "by_unit": [{"unit": r[0], "entries": _int(r[1]), "quantity": _int(r[2])} for r in by_unit],
        "by_category": rows(by_category),
        "by_severity": rows(by_severity),
        "by_product": rows(by_product),
    }


# --------------------------------------------------------------------------------------
# Disposition (rework / rejection)
# --------------------------------------------------------------------------------------
def disposition_report(f: ReportFilters) -> dict:
    conds = _inspection_conditions(f)
    recorded = db.session.execute(
        select(
            Inspection.quantity_unit,
            func.count(Inspection.id),
            func.sum(Inspection.inspected_quantity),
            func.sum(DispositionRecord.accepted_quantity),
            func.sum(DispositionRecord.rework_quantity),
            func.sum(DispositionRecord.rejected_quantity),
            func.sum(DispositionRecord.pending_quantity),
        )
        .select_from(Inspection)
        .join(DispositionRecord, DispositionRecord.inspection_id == Inspection.id)
        .where(*conds)
        .group_by(Inspection.quantity_unit)
        .order_by(Inspection.quantity_unit)
    ).all()
    missing = db.session.execute(
        select(Inspection.quantity_unit, func.count(Inspection.id), func.sum(Inspection.inspected_quantity))
        .where(
            *conds,
            ~select(DispositionRecord.id)
            .where(DispositionRecord.inspection_id == Inspection.id)
            .correlate(Inspection)
            .exists(),
        )
        .group_by(Inspection.quantity_unit)
        .order_by(Inspection.quantity_unit)
    ).all()
    rows = []
    for unit, count, inspected, accepted, rework, rejected, pending in recorded:
        inspected, rework, rejected = _int(inspected), _int(rework), _int(rejected)
        rows.append(
            {
                "unit": unit,
                "inspections": _int(count),
                "inspected": inspected,
                "accepted": _int(accepted),
                "rework": rework,
                "rejected": rejected,
                "pending": _int(pending),
                "rework_rate": rate_percent(rework, inspected),
                "rejection_rate": rate_percent(rejected, inspected),
            }
        )
    return {
        "recorded": rows,
        "not_recorded": [
            {"unit": r[0], "inspections": _int(r[1]), "inspected": _int(r[2])} for r in missing
        ],
    }


# --------------------------------------------------------------------------------------
# Trend
# --------------------------------------------------------------------------------------
def trend_report(f: ReportFilters, interval: str = "month") -> dict:
    """Period summaries. Periods without any matching record are simply not listed."""
    if interval not in INTERVALS:
        interval = "month"
    conds = _inspection_conditions(f)

    inspections = db.session.execute(
        select(
            Inspection.inspection_date,
            Inspection.quantity_unit,
            func.count(Inspection.id),
            func.sum(Inspection.inspected_quantity),
        )
        .where(*conds)
        .group_by(Inspection.inspection_date, Inspection.quantity_unit)
    ).all()
    dispositions = db.session.execute(
        select(
            Inspection.inspection_date,
            Inspection.quantity_unit,
            func.sum(Inspection.inspected_quantity),
            func.sum(DispositionRecord.rework_quantity),
            func.sum(DispositionRecord.rejected_quantity),
        )
        .select_from(Inspection)
        .join(DispositionRecord, DispositionRecord.inspection_id == Inspection.id)
        .where(*conds)
        .group_by(Inspection.inspection_date, Inspection.quantity_unit)
    ).all()
    defects = db.session.execute(
        select(
            Inspection.inspection_date,
            DefectEntry.quantity_unit,
            func.count(DefectEntry.id),
            func.sum(DefectEntry.defect_quantity),
        )
        .select_from(DefectEntry)
        .join(Inspection, DefectEntry.inspection_id == Inspection.id)
        .where(*conds, *_defect_conditions(f))
        .group_by(Inspection.inspection_date, DefectEntry.quantity_unit)
    ).all()

    activity: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"inspections": 0, "inspected": 0, "disp_inspected": 0, "rework": 0, "rejected": 0}
    )
    for day, unit, count, qty in inspections:
        row = activity[(period_key(day, interval), unit)]
        row["inspections"] += _int(count)
        row["inspected"] += _int(qty)
    for day, unit, qty, rework, rejected in dispositions:
        row = activity[(period_key(day, interval), unit)]
        row["disp_inspected"] += _int(qty)
        row["rework"] += _int(rework)
        row["rejected"] += _int(rejected)

    defect_rows: dict[tuple[str, str], dict] = defaultdict(lambda: {"entries": 0, "quantity": 0})
    for day, unit, count, qty in defects:
        row = defect_rows[(period_key(day, interval), unit)]
        row["entries"] += _int(count)
        row["quantity"] += _int(qty)

    return {
        "interval": interval,
        "activity": [
            {
                "period": key,
                "label": period_label(key, interval),
                "unit": unit,
                **values,
                "rework_rate": rate_percent(values["rework"], values["disp_inspected"]),
                "rejection_rate": rate_percent(values["rejected"], values["disp_inspected"]),
            }
            for (key, unit), values in sorted(activity.items())
        ],
        "defects": [
            {"period": key, "label": period_label(key, interval), "unit": unit, **values}
            for (key, unit), values in sorted(defect_rows.items())
        ],
    }


# --------------------------------------------------------------------------------------
# Corrective actions
# --------------------------------------------------------------------------------------
def _action_conditions(f: ReportFilters) -> list:
    conditions = []
    if f.date_from:
        conditions.append(func.date(CorrectiveAction.created_at) >= f.date_from.isoformat())
    if f.date_to:
        conditions.append(func.date(CorrectiveAction.created_at) <= f.date_to.isoformat())
    inspection_filters = ReportFilters(product=f.product, batch=f.batch, stage=f.stage)
    inspection_conds = _inspection_conditions(inspection_filters)
    if inspection_conds:
        conditions.append(
            CorrectiveAction.inspection_id.in_(select(Inspection.id).where(*inspection_conds).correlate(None))
        )
    defect_conditions = _defect_conditions(f)
    if defect_conditions:
        conditions.append(
            CorrectiveAction.defect_entry_id.in_(select(DefectEntry.id).where(*defect_conditions).correlate(None))
        )
    return conditions


def corrective_action_report(f: ReportFilters, today: date | None = None) -> dict:
    today = today or date.today()
    conds = _action_conditions(f)
    counts = dict(
        db.session.execute(
            select(CorrectiveAction.status, func.count(CorrectiveAction.id))
            .where(*conds)
            .group_by(CorrectiveAction.status)
        ).all()
    )
    overdue_conditions = [
        *conds,
        CorrectiveAction.target_date.is_not(None),
        CorrectiveAction.target_date < today,
        CorrectiveAction.status.in_(sorted(workflow.OVERDUE_ELIGIBLE)),
    ]
    overdue = list(
        db.session.execute(
            select(CorrectiveAction, Inspection)
            .join(Inspection, CorrectiveAction.inspection_id == Inspection.id)
            .where(*overdue_conditions)
            .order_by(CorrectiveAction.target_date, CorrectiveAction.id)
            .limit(100)
        ).all()
    )
    awaiting = list(
        db.session.execute(
            select(CorrectiveAction, Inspection)
            .join(Inspection, CorrectiveAction.inspection_id == Inspection.id)
            .where(*conds, CorrectiveAction.status == workflow.COMPLETED)
            .order_by(CorrectiveAction.completed_on, CorrectiveAction.id)
            .limit(100)
        ).all()
    )
    return {
        "total": sum(counts.values()),
        "by_status": [
            {"status": s, "label": workflow.status_label(s), "count": _int(counts.get(s))}
            for s in workflow.STATUSES
        ],
        "overdue": overdue,
        "awaiting_followup": awaiting,
    }


# --------------------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------------------
def default_dashboard_period(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    return today - timedelta(days=DEFAULT_DASHBOARD_DAYS - 1), today


def dashboard_summary(f: ReportFilters) -> dict:
    """Uses exactly the same functions as the report screens so the figures always agree."""
    total_all_time = _int(db.session.scalar(select(func.count(Inspection.id))))
    return {
        "total_inspections_all_time": total_all_time,
        "inspections": inspection_summary(f),
        "defects": defect_analysis(f),
        "disposition": disposition_report(f),
        # Corrective actions: current status of ALL recorded actions (not limited to the period).
        "actions": corrective_action_report(ReportFilters()),
    }
