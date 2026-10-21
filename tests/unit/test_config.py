import pytest

from app import config


def test_unknown_environment_is_rejected():
    with pytest.raises(RuntimeError):
        config.load_config("staging")


def test_production_requires_secret_key(monkeypatch):
    monkeypatch.delenv("TQI_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TQI_SECRET_KEY"):
        config.load_config("production")


def test_environment_values_are_used(monkeypatch, tmp_path):
    monkeypatch.setenv("TQI_SECRET_KEY", "abc")
    monkeypatch.setenv("TQI_DATABASE_PATH", str(tmp_path / "x.db"))
    loaded = config.load_config("testing")
    assert loaded["SECRET_KEY"] == "abc"
    assert loaded["TESTING"] is True
    assert loaded["DATABASE_PATH"].endswith("x.db")
    assert loaded["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///")
    assert loaded["WTF_CSRF_ENABLED"] is True
    assert loaded["DEBUG"] is False


def test_relative_database_path_is_resolved_against_project(monkeypatch):
    path = config.resolve_database_path("data/my.db")
    assert path.is_absolute()
    assert path.parent.name == "data"
