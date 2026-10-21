from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domain.errors import BusinessRuleError, ValidationError
from app.extensions import db
from app.models import DefectEntry, Inspection
from app.services import (
    corrective_action_service as cas,
)
from app.services import (
    defect_service,
    disposition_service,
    inspection_service,
)
from tests.integration.conftest import defect_row, inspection_form


def make_inspection(reference, qty="1000", defects=((0, None),), **overrides):
    rows = [(i, defect_row(reference["hole"], reference["major"], **(extra or {}))) for i, extra in defects]
    return inspection_service.create_inspection(inspection_form(inspected_quantity=qty, **overrides), rows)


def test_create_inspection_with_defects_is_saved_together(reference):
    insp = make_inspection(reference, defects=((0, None), (1, {"quantity": "5"})))
    assert insp.inspection_code.startswith("INS-")
    assert insp.quantity_unit == "meters"  # units are normalised to lower case
    assert db.session.query(DefectEntry).count() == 2


def test_invalid_defect_rolls_back_the_whole_inspection(reference):
    rows = [(0, defect_row(reference["hole"])), (1, defect_row(reference["stain"], quantity="abc"))]
    with pytest.raises(ValidationError) as exc:
        inspection_service.create_inspection(inspection_form(), rows)
    assert "defect-1-defect_quantity" in exc.value.errors
    assert db.session.query(Inspection).count() == 0
    assert db.session.query(DefectEntry).count() == 0


def test_defect_unit_must_match_inspection_unit(reference):
    rows = [(0, defect_row(reference["hole"], unit="kg"))]
    with pytest.raises(ValidationError):
        inspection_service.create_inspection(inspection_form(), rows)


def test_foreign_keys_are_enforced_by_sqlite(reference):
    insp = make_inspection(reference)
    with pytest.raises(IntegrityError):
        db.session.execute(text("DELETE FROM inspections WHERE id = :i"), {"i": insp.id})
        db.session.commit()
    db.session.rollback()


def test_inspection_with_history_cannot_be_deleted(reference):
    insp = make_inspection(reference)
    with pytest.raises(BusinessRuleError):
        inspection_service.delete_inspection(insp.id)
    assert db.session.get(Inspection, insp.id) is not None


def test_empty_inspection_can_be_deleted(reference):
    insp = inspection_service.create_inspection(inspection_form(), [])
    inspection_service.delete_inspection(insp.id)
    assert db.session.get(Inspection, insp.id) is None


def test_category_names_are_unique_ignoring_case(reference):
    with pytest.raises(ValidationError):
        defect_service.create_category({"name": "  HOLE "})


def test_disposition_must_reconcile(reference):
    insp = make_inspection(reference)
    bad = {"accepted_quantity": "900", "rework_quantity": "50", "rejected_quantity": "30", "pending_quantity": "0"}
    with pytest.raises(ValidationError):
        disposition_service.save_disposition(insp.id, bad)
    assert disposition_service.get_disposition(insp.id) is None
    good = {**bad, "pending_quantity": "20"}
    record = disposition_service.save_disposition(insp.id, good)
    assert record.total == 1000
    # saving again updates the single record
    disposition_service.save_disposition(insp.id, {**good, "accepted_quantity": "920", "pending_quantity": "0"})
    assert disposition_service.get_disposition(insp.id).accepted_quantity == 920


def test_inspected_quantity_cannot_be_changed_to_break_disposition(reference):
    insp = make_inspection(reference)
    disposition_service.save_disposition(
        insp.id,
        {"accepted_quantity": "1000", "rework_quantity": "0", "rejected_quantity": "0", "pending_quantity": "0"},
    )
    with pytest.raises(ValidationError):
        inspection_service.update_inspection(insp.id, inspection_form(inspected_quantity="900"))


def action_data(insp, **extra):
    data = {"inspection_id": str(insp.id), "problem_description": "Holes in warp",
            "action_description": "Replace heddles", "responsible_person": "Asha",
            "target_date": "2026-10-10"}
    data.update(extra)
    return data


def test_corrective_action_workflow_requires_followup(reference, monkeypatch):
    monkeypatch.setattr(cas, "today", lambda: date(2026, 10, 20))
    insp = make_inspection(reference)
    action = cas.create_action(action_data(insp))
    assert action.status == "open"

    cas.change_status(action.id, "in_progress", {})
    cas.change_status(action.id, "completed_awaiting_followup", {"completed_on": "2026-10-12"})

    # completion is not effectiveness: no follow-up yet
    with pytest.raises(ValidationError):
        cas.change_status(action.id, "effective", {})

    cas.add_followup(action.id, {"follow_up_date": "2026-10-15", "result": "effective",
                                 "observations": "No holes in next 3 lots"})
    cas.change_status(action.id, "effective", {})
    cas.change_status(action.id, "closed", {})
    with pytest.raises(ValidationError):
        cas.change_status(action.id, "open", {})


def test_followup_only_allowed_while_awaiting_followup(reference, monkeypatch):
    monkeypatch.setattr(cas, "today", lambda: date(2026, 10, 20))
    insp = make_inspection(reference)
    action = cas.create_action(action_data(insp))
    with pytest.raises(BusinessRuleError):
        cas.add_followup(action.id, {"follow_up_date": "2026-10-15", "result": "effective", "observations": "x"})


def test_action_must_link_defect_of_same_inspection(reference):
    first = make_inspection(reference)
    second = make_inspection(reference)
    foreign_defect = second.defects[0]
    with pytest.raises(ValidationError):
        cas.create_action(action_data(first, defect_entry_id=str(foreign_defect.id)))


def test_defect_with_actions_cannot_be_deleted(reference):
    insp = make_inspection(reference)
    defect = insp.defects[0]
    cas.create_action(action_data(insp, defect_entry_id=str(defect.id)))
    with pytest.raises(BusinessRuleError):
        defect_service.delete_defect(defect.id)


def test_search_treats_wildcards_literally(reference):
    inspection_service.create_inspection(inspection_form(product_reference="Plain 100%"), [])
    inspection_service.create_inspection(inspection_form(product_reference="Twill"), [])
    page = inspection_service.list_inspections(inspection_service.InspectionFilters(q="%"), 1, 25)
    assert page.total == 1
