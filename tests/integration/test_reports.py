"""Report figures checked against a small hand-computed dataset."""

from datetime import date
from decimal import Decimal

import pytest

from app.services import corrective_action_service as cas
from app.services import disposition_service, inspection_service
from app.services import reporting_service as rs
from tests.integration.conftest import defect_row, inspection_form


def disp(a, r, j, p):
    return {"accepted_quantity": str(a), "rework_quantity": str(r), "rejected_quantity": str(j), "pending_quantity": str(p)}


@pytest.fixture()
def dataset(reference):
    h, s, major, minor = reference["hole"], reference["stain"], reference["major"], reference["minor"]
    # 1: 1000 m, two defect entries (10 + 5), disposition 900/50/30/20
    a = inspection_service.create_inspection(
        inspection_form(inspection_date="2026-10-01", product_reference="Twill"),
        [(0, defect_row(h, major, "10")), (1, defect_row(s, minor, "5"))],
    )
    disposition_service.save_disposition(a.id, disp(900, 50, 30, 20))
    # 2: 500 m, no defects, no disposition recorded
    b = inspection_service.create_inspection(
        inspection_form(inspection_date="2026-10-15", product_reference="Twill", inspected_quantity="500"), []
    )
    # 3: 200 pieces (different unit), one defect without severity, disposition 190/0/10/0
    c = inspection_service.create_inspection(
        inspection_form(inspection_date="2026-11-02", product_reference="Shirt", inspected_quantity="200",
                        quantity_unit="pieces"),
        [(0, defect_row(h, None, "4", unit="pieces"))],
    )
    disposition_service.save_disposition(c.id, disp(190, 0, 10, 0))
    return a, b, c


def test_units_are_never_combined(dataset):
    summary = rs.inspection_summary(rs.ReportFilters())
    by_unit = {r["unit"]: r for r in summary["by_unit"]}
    assert by_unit["meters"]["inspections"] == 2 and by_unit["meters"]["quantity"] == 1500
    assert by_unit["pieces"]["quantity"] == 200


def test_entry_count_differs_from_defect_quantity(dataset):
    result = rs.defect_analysis(rs.ReportFilters())
    assert result["entries"] == 3
    by_unit = {r["unit"]: r for r in result["by_unit"]}
    assert by_unit["meters"]["entries"] == 2 and by_unit["meters"]["quantity"] == 15


def test_rates_use_only_inspections_with_a_disposition(dataset):
    result = rs.disposition_report(rs.ReportFilters())
    meters = next(r for r in result["recorded"] if r["unit"] == "meters")
    assert meters["inspected"] == 1000  # the 500 m inspection has no disposition
    assert meters["rework_rate"] == Decimal("5.00")
    assert meters["rejection_rate"] == Decimal("3.00")
    assert any(r["unit"] == "meters" and r["inspections"] == 1 for r in result["not_recorded"])


def test_date_filter_is_inclusive(dataset):
    f = rs.ReportFilters(date_from=date(2026, 10, 1), date_to=date(2026, 10, 15))
    assert rs.inspection_summary(f)["total_inspections"] == 2
    f = rs.ReportFilters(date_from=date(2026, 10, 2), date_to=date(2026, 10, 14))
    assert rs.inspection_summary(f)["total_inspections"] == 0


def test_empty_database_gives_not_applicable_not_zero_percent(reference):
    result = rs.disposition_report(rs.ReportFilters())
    assert result["recorded"] == []


def test_monthly_trend(dataset):
    trend = rs.trend_report(rs.ReportFilters(), "month")
    labels = {(r["label"], r["unit"]) for r in trend["activity"]}
    assert labels == {("2026-10", "meters"), ("2026-11", "pieces")}


def test_overdue_excludes_actions_without_target_date(dataset, monkeypatch):
    a, _, _ = dataset
    monkeypatch.setattr(cas, "today", lambda: date(2026, 10, 20))
    cas.create_action({"inspection_id": str(a.id), "problem_description": "late", "target_date": "2026-10-05"})
    cas.create_action({"inspection_id": str(a.id), "problem_description": "no date"})
    report = rs.corrective_action_report(rs.ReportFilters(), today=date(2026, 10, 20))
    assert len(report["overdue"]) == 1
    assert report["total"] == 2
