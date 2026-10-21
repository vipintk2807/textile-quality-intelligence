"""Render every page template with sample data.

Needs only Flask + Jinja (no database), so it can run where SQLAlchemy is unavailable.
It uses StrictUndefined, so a template that references a missing variable fails here
instead of at runtime. It checks rendering and escaping, not database behaviour.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

flask = pytest.importorskip("flask")
import jinja2  # noqa: E402

from app import template_helpers as th  # noqa: E402
from app.domain import workflow  # noqa: E402
from app.domain.disposition import DISPOSITION_STATUS_LABELS  # noqa: E402
from app.domain.validation import LIMITS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / "app"

ROUTES = {
    "dashboard.index": "/",
    "inspections.list_view": "/inspections/",
    "inspections.create": "/inspections/new",
    "inspections.detail": "/inspections/<int:inspection_id>",
    "inspections.edit": "/inspections/<int:inspection_id>/edit",
    "inspections.delete": "/inspections/<int:inspection_id>/delete",
    "inspections.disposition": "/inspections/<int:inspection_id>/disposition",
    "inspections.disposition_delete": "/inspections/<int:inspection_id>/disposition/delete",
    "inspections.add_defect": "/inspections/<int:inspection_id>/defects/new",
    "defects.list_view": "/defects/",
    "defects.edit": "/defects/<int:defect_id>/edit",
    "defects.delete": "/defects/<int:defect_id>/delete",
    "defects.categories": "/defects/categories",
    "defects.severities": "/defects/severities",
    "actions.list_view": "/actions/",
    "actions.create": "/actions/new",
    "actions.detail": "/actions/<int:action_id>",
    "actions.edit": "/actions/<int:action_id>/edit",
    "actions.change_status": "/actions/<int:action_id>/status",
    "actions.add_followup": "/actions/<int:action_id>/followup",
    "reports.index": "/reports/",
    "data.index": "/data/",
    "data.backup": "/data/backup",
}


@pytest.fixture()
def app():
    app = flask.Flask("app", root_path=str(ROOT))
    app.config.update(SECRET_KEY="x", MAX_DEFECTS_PER_FORM=50, TESTING=True)
    app.jinja_env.undefined = jinja2.StrictUndefined
    for endpoint, rule in ROUTES.items():
        app.add_url_rule(rule, endpoint, lambda **_: "", methods=["GET", "POST"])
    app.jinja_env.globals["csrf_token"] = lambda: "TOKEN"
    app.add_template_filter(th.fmt_date, "fmt_date")
    app.add_template_filter(th.fmt_datetime, "fmt_datetime")
    app.add_template_filter(th.fmt_qty, "qty")
    app.add_template_filter(th.fmt_rate, "rate")
    app.add_template_filter(workflow.status_label, "status_label")
    app.add_template_global(DISPOSITION_STATUS_LABELS, "disposition_labels")

    @app.context_processor
    def ctx():
        return {
            "nav_items": th.NAV_ITEMS,
            "current_section": "dashboard",
            "limits": LIMITS,
            "action_statuses": workflow.STATUSES,
            "action_status_labels": workflow.STATUS_LABELS,
            "followup_labels": workflow.FOLLOWUP_LABELS,
            "today_iso": "2026-10-18",
            "NOT_APPLICABLE": th.NOT_APPLICABLE,
        }

    return app


def page(items, total=None, page_no=1, per=25):
    total = len(items) if total is None else total
    return NS(
        items=items, page=page_no, per_page=per, total=total, pages=1,
        has_prev=False, has_next=False,
        first_item=1 if items else 0, last_item=len(items),
    )


XSS = '<script>alert("x")</script>'


def inspection(**kw):
    base = dict(
        id=1, inspection_code="INS-20261018-0001", inspection_date=date(2026, 10, 18),
        product_reference=XSS, batch_reference="B1", production_stage="Weaving",
        inspection_type="Final", inspected_quantity=1000, quantity_unit="meters",
        inspector_name="A", notes="n", created_at=datetime(2026, 10, 18, 9, 0),
        defects=[], disposition=None, corrective_actions=[],
    )
    base.update(kw)
    return NS(**base)


CAT = NS(id=1, name="Hole", is_active=True, description=None, sort_order=0)
SEV = NS(id=2, name="Major", is_active=True, description=None, sort_order=1)
DEFECT = NS(
    id=5, inspection_id=1, category_id=1, severity_id=2, category=CAT, severity=SEV,
    defect_quantity=3, quantity_unit="meters", suspected_cause=XSS, observations=None,
)
DISP = NS(
    accepted_quantity=900, rework_quantity=50, rejected_quantity=30, pending_quantity=20,
    quantity_unit="meters", notes=None, total=1000,
)
ACTION = NS(
    id=7, inspection_id=1, inspection=inspection(), defect_entry_id=5, defect_entry=DEFECT,
    problem_description=XSS, suspected_cause=None, confirmed_root_cause=None,
    action_description="Fix", responsible_person="R", target_date=date(2026, 10, 1),
    completed_on=None, status="open", notes=None, follow_ups=[],
)
FORM_CTX = dict(
    categories=[CAT], severities=[SEV], unit_suggestions=("pieces",), stage_suggestions=["Weaving"]
)


def render(app, template, **ctx):
    with app.test_request_context("/"):
        return flask.render_template(template, **ctx)


def test_error_page(app):
    assert "Page not found" in render(app, "error.html", title="Page not found", message="m", status=404)


def test_inspection_pages(app):
    insp = inspection()
    html = render(
        app, "inspections/list.html",
        page=page([(insp, 2, None), (insp, 0, DISP)]),
        filters=NS(q="", date_from=None, date_to=None, product="", batch="", stage="",
                   disposition="", active=False),
        errors={}, qs={}, products=["P"], batches=["B"], stages=["S"],
        disposition_status=lambda d: "not_recorded" if d is None else "resolved",
    )
    assert XSS not in html and "&lt;script&gt;" in html
    render(app, "inspections/list.html", page=page([]),
           filters=NS(q="x", date_from=None, date_to=None, product="", batch="", stage="",
                      disposition="", active=True),
           errors={}, qs={"q": "x"}, products=[], batches=[], stages=[],
           disposition_status=lambda d: "not_recorded")
    render(app, "inspections/form.html", inspection=None, form={}, errors={}, rows=[], **FORM_CTX)
    html = render(
        app, "inspections/form.html", inspection=None,
        form={"product_reference": XSS},
        errors={"product_reference": "Required.", "defect-3-category_id": "Select a defect category."},
        rows=[(3, {"defect_quantity": "2", "category_id": "1"})], **FORM_CTX,
    )
    assert XSS not in html and "Select a defect category." in html
    assert 'data-next="4"' in html and "__INDEX__" in html
    insp_ = inspection()
    render(app, "inspections/form.html", inspection=insp_, form={}, errors={}, rows=[], **FORM_CTX)
    insp_.defects = [DEFECT]
    for disp, state in ((None, "not_recorded"), (DISP, "pending")):
        html = render(
            app, "inspections/detail.html", inspection=insp_, defects=[DEFECT], disposition=disp,
            disposition_state=state, actions=[ACTION], dependencies={}, today=date(2026, 10, 18),
        )
        assert XSS not in html
    render(app, "inspections/disposition.html", inspection=insp_, record=DISP, form={}, errors={})
    render(app, "inspections/disposition.html", inspection=insp_, record=None,
           form={"accepted_quantity": "5"}, errors={"pending_quantity": "Too many."})


def test_defect_pages(app):
    insp = inspection()
    render(app, "defects/list.html", page=page([(DEFECT, insp, CAT, SEV), (DEFECT, insp, CAT, None)]),
           filters=NS(category_id=None, severity_id=None, q=""), qs={}, categories=[CAT], severities=[SEV])
    render(app, "defects/form.html", inspection=insp, defect=None, form={}, errors={}, **FORM_CTX)
    render(app, "defects/form.html", inspection=insp, defect=DEFECT, form={}, errors={}, **FORM_CTX)
    render(app, "defects/form.html", inspection=insp, defect=DEFECT,
           form={"defect_quantity": "x"}, errors={"defect_quantity": "Enter a whole number."}, **FORM_CTX)
    for sortable in (False, True):
        render(app, "defects/reference.html", kind="category", title="T", items=[CAT, SEV], editing=None,
               form={}, errors={}, endpoint="defects.categories", sortable=sortable)
        render(app, "defects/reference.html", kind="category", title="T", items=[], editing=SEV,
               form={"name": "x"}, errors={"name": "dup"}, endpoint="defects.categories", sortable=sortable)


def test_action_pages(app):
    insp = inspection()
    render(app, "corrective_actions/list.html", page=page([(ACTION, insp)]),
           filters=NS(q="", status="", responsible="", product="", batch="", overdue_only=False),
           qs={}, today=date(2026, 10, 18), is_overdue=workflow.is_overdue,
           products=["P"], batches=["B"], responsible_people=["R"])
    for action in (None, ACTION):
        render(app, "corrective_actions/form.html", action=action, form={}, errors={},
               inspections=[insp], defects=[DEFECT], selected_inspection=1, selected_defect=5)
    render(app, "corrective_actions/form.html", action=None, form={"problem_description": ""},
           errors={"problem_description": "Required."}, inspections=[insp], defects=[],
           selected_inspection=None, selected_defect=None)
    done = NS(**{**ACTION.__dict__, "status": "completed_awaiting_followup"})
    fu = NS(follow_up_date=date(2026, 10, 10), result="effective", observations=XSS, recorded_by=None)
    for action, nxt, section, errors in (
        (ACTION, ["in_progress", "completed_awaiting_followup"], None, {}),
        (done, ["effective", "not_effective", "in_progress"], "followup", {"result": "Select the assessment result."}),
        (done, [], "status", {"status": "Not allowed."}),
    ):
        html = render(
            app, "corrective_actions/detail.html", action=action, inspection=insp, followups=[fu],
            next_statuses=nxt, overdue=True, today=date(2026, 10, 18), form={}, errors=errors,
            error_section=section,
        )
        assert XSS not in html


def test_report_and_dashboard_pages(app):
    filters = NS(describe=lambda: ["All inspection dates"], date_from=None, date_to=date(2026, 10, 18))
    common = dict(views=(("summary", "S"), ("defects", "D"), ("disposition", "P"), ("trend", "T"), ("actions", "A")),
                  interval="month", intervals=("day", "week", "month"), filters=filters, errors={},
                  form={}, categories=[CAT], severities=[SEV], products=[], batches=[], stages=[])
    unit_row = {"label": "Blue", "unit": "meters", "entries": 2, "inspections": 2, "quantity": 10}
    data = {
        "summary": {"total_inspections": 2, "by_unit": [{"unit": "m", "inspections": 2, "quantity": 5}],
                    "by_product": [unit_row], "by_stage": []},
        "defects": {"entries": 2, "inspections_with_defects": 1, "by_unit": [{"unit": "m", "entries": 2, "quantity": 5}],
                    "by_category": [unit_row], "by_severity": [], "by_product": []},
        "disposition": {"recorded": [{"unit": "m", "inspections": 1, "inspected": 100, "accepted": 90, "rework": 5,
                                      "rejected": 5, "pending": 0, "rework_rate": Decimal("5.00"),
                                      "rejection_rate": None}],
                        "not_recorded": [{"unit": "m", "inspections": 1, "inspected": 10}]},
        "trend": {"interval": "month", "activity": [{"label": "2026-10", "unit": "m", "inspections": 1, "inspected": 5,
                                                     "rework_rate": None, "rejection_rate": None}],
                  "defects": [{"label": "2026-10", "unit": "m", "entries": 1, "quantity": 2}]},
        "actions": {"total": 1, "by_status": [{"status": "open", "label": "Open", "count": 1}],
                    "overdue": [(ACTION, inspection())], "awaiting_followup": [(ACTION, inspection())]},
    }
    for view, payload in data.items():
        html = render(app, "reports/index.html", view=view, data=payload, **common)
        assert XSS not in html
    render(app, "reports/index.html", view="summary", data=None, **{**common, "errors": {"date_to": "bad"}})
    for empty in ({"summary": {"total_inspections": 0, "by_unit": [], "by_product": [], "by_stage": []}},):
        render(app, "reports/index.html", view="summary", data=empty["summary"], **common)

    summary = {
        "total_inspections_all_time": 3,
        "inspections": data["summary"], "defects": data["defects"], "disposition": data["disposition"],
        "actions": data["actions"],
    }
    insp = inspection()
    render(app, "dashboard.html", summary=summary, filters=filters, errors={}, recent=[(insp, 1, None), (insp, 0, DISP)])
    empty_summary = {**summary, "total_inspections_all_time": 0}
    render(app, "dashboard.html", summary=empty_summary, filters=filters, errors={}, recent=[])


def test_data_management_page(app):
    status = NS(exists=True, size_bytes=1024, integrity_ok=True, integrity_detail="ok", schema_ok=True,
                schema_revision="0001_initial", missing_tables=(), error=None)
    render(app, "data_management/index.html", status=status, db_path="x.db", backup_dir="b",
           backups=[{"name": "tqi-backup-1.db", "size": 10, "created": datetime(2026, 10, 18)}])
    missing = NS(exists=False, size_bytes=0, integrity_ok=None, integrity_detail="", schema_ok=False,
                 schema_revision=None, missing_tables=("inspections",), error="not created")
    render(app, "data_management/index.html", status=missing, db_path="x.db", backup_dir="b", backups=[])
