"""Backup / restore use only the standard-library sqlite3 module, so they run anywhere."""

import sqlite3

import pytest

from app.services import data_management_service as dm


def make_db(path, *, with_schema=True, rows=0):
    con = sqlite3.connect(path)
    if with_schema:
        for table in dm.REQUIRED_TABLES:
            con.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, label TEXT)")
        for i in range(rows):
            con.execute("INSERT INTO inspections (label) VALUES (?)", (f"row {i}",))
    con.commit()
    con.close()


def count(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT count(*) FROM inspections").fetchone()[0]
    finally:
        con.close()


def test_status_of_missing_database_does_not_create_it(tmp_path):
    target = tmp_path / "none.db"
    status = dm.database_status(target)
    assert not status.exists and not target.exists()


def test_status_reports_missing_tables(tmp_path):
    db = tmp_path / "a.db"
    make_db(db, with_schema=False)
    status = dm.database_status(db)
    assert status.exists and status.integrity_ok and not status.schema_ok
    assert "inspections" in status.missing_tables


def test_backup_is_verified_copy_and_never_overwrites(tmp_path):
    db = tmp_path / "a.db"
    make_db(db, rows=3)
    first = dm.create_backup(db, tmp_path / "backups")
    second = dm.create_backup(db, tmp_path / "backups")
    assert first != second and first.exists() and second.exists()
    assert count(first) == 3
    assert len(dm.list_backups(tmp_path / "backups")) == 2


def test_backup_without_database_fails_clearly(tmp_path):
    with pytest.raises(dm.BackupError):
        dm.create_backup(tmp_path / "missing.db", tmp_path / "b")


def test_restore_replaces_database_and_preserves_previous(tmp_path):
    db = tmp_path / "live.db"
    make_db(db, rows=2)
    backup = dm.create_backup(db, tmp_path / "b")
    make_db(tmp_path / "extra.db", rows=0)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO inspections (label) VALUES ('later')")
    con.commit()
    con.close()
    assert count(db) == 3

    preserved = dm.restore_backup(backup, db)
    assert count(db) == 2
    assert preserved is not None and count(preserved) == 3


@pytest.mark.parametrize("kind", ["not_a_database", "wrong_schema", "missing"])
def test_invalid_backup_is_rejected_and_live_data_untouched(tmp_path, kind):
    db = tmp_path / "live.db"
    make_db(db, rows=2)
    bad = tmp_path / "bad.db"
    if kind == "not_a_database":
        bad.write_bytes(b"this is not sqlite" * 50)
    elif kind == "wrong_schema":
        make_db(bad, with_schema=False)
    else:
        bad = tmp_path / "nope.db"
    with pytest.raises(dm.BackupError):
        dm.restore_backup(bad, db)
    assert count(db) == 2
