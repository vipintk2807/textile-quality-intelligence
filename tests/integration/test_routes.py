import pytest

from app.extensions import db
from app.models import Inspection
from tests.integration.conftest import build_app, inspection_form

GET_PAGES = [
    "/", "/inspections/", "/inspections/new", "/defects/", "/defects/categories",
    "/defects/severities", "/actions/", "/actions/new", "/reports/", "/reports/?view=defects",
    "/reports/?view=disposition", "/reports/?view=trend", "/reports/?view=actions", "/data/",
]


@pytest.mark.parametrize("url", GET_PAGES)
def test_pages_render_on_an_empty_database(client, url):
    assert client.get(url).status_code == 200


def test_unknown_page_and_record_give_friendly_404(client):
    assert client.get("/nope").status_code == 404
    response = client.get("/inspections/999")
    assert response.status_code == 404
    assert b"Traceback" not in response.data


def test_create_inspection_through_the_form(client, reference):
    data = inspection_form()
    data.update({"defect-0-category_id": str(reference["hole"].id), "defect-0-defect_quantity": "7",
                 "defect-0-quantity_unit": "meters"})
    response = client.post("/inspections/new", data=data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Cotton twill" in response.data
    assert db.session.query(Inspection).count() == 1


def test_invalid_form_keeps_input_and_saves_nothing(client):
    data = inspection_form(inspected_quantity="-5", product_reference="Keep me")
    response = client.post("/inspections/new", data=data)
    assert response.status_code == 400
    assert b"Keep me" in response.data
    assert db.session.query(Inspection).count() == 0


def test_user_text_is_escaped(client):
    client.post("/inspections/new", data=inspection_form(product_reference="<script>alert(1)</script>"))
    page = client.get("/inspections/").data
    assert b"<script>alert(1)</script>" not in page
    assert b"&lt;script&gt;" in page


def test_csrf_blocks_post_without_token(tmp_path, monkeypatch):
    application = build_app(tmp_path, monkeypatch, csrf=True)
    with application.app_context():
        db.create_all()
        response = application.test_client().post("/inspections/new", data=inspection_form())
        assert response.status_code == 400
        assert db.session.query(Inspection).count() == 0
        db.session.remove()
        db.engine.dispose()


def test_backup_button_creates_a_verified_file(client, app, tmp_path):
    client.post("/inspections/new", data=inspection_form())
    response = client.post("/data/backup", follow_redirects=True)
    assert response.status_code == 200
    assert list((tmp_path / "backups").glob("tqi-backup-*.db"))


def test_data_persists_after_reopening_the_database(tmp_path, monkeypatch):
    first = build_app(tmp_path, monkeypatch)
    with first.app_context():
        db.create_all()
        first.test_client().post("/inspections/new", data=inspection_form())
        db.session.remove()
        db.engine.dispose()
    second = build_app(tmp_path, monkeypatch)
    with second.app_context():
        assert db.session.query(Inspection).count() == 1
        db.session.remove()
        db.engine.dispose()
