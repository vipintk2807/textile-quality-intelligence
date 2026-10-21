"""Database status, SQLite-safe backup and restore.

Backups use SQLite's own backup API (a consistent snapshot even while the database is
open) and are verified with ``PRAGMA integrity_check`` before being reported as
successful. Existing backup files are never overwritten.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

REQUIRED_TABLES = (
    "inspections",
    "defect_categories",
    "severity_levels",
    "defect_entries",
    "disposition_records",
    "corrective_actions",
    "action_follow_ups",
)


class BackupError(Exception):
    """Backup or restore failed (the message is safe to show to the user)."""


@dataclass
class DatabaseStatus:
    exists: bool
    size_bytes: int = 0
    integrity_ok: bool | None = None
    integrity_detail: str = ""
    schema_revision: str | None = None
    missing_tables: tuple[str, ...] = ()
    error: str | None = None

    @property
    def schema_ok(self) -> bool:
        return self.exists and not self.missing_tables and self.error is None


def _integrity(path: Path) -> tuple[bool, str]:
    connection = sqlite3.connect(str(path))
    try:
        rows = connection.execute("PRAGMA integrity_check").fetchall()
    finally:
        connection.close()
    detail = "; ".join(str(r[0]) for r in rows)
    return detail.strip().lower() == "ok", detail


def database_status(db_path: str | Path) -> DatabaseStatus:
    """Inspect the database file WITHOUT creating it if it does not exist."""
    path = Path(db_path)
    if not path.exists():
        return DatabaseStatus(exists=False, error="The database file has not been created yet.")
    status = DatabaseStatus(exists=True, size_bytes=path.stat().st_size)
    try:
        status.integrity_ok, status.integrity_detail = _integrity(path)
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            status.missing_tables = tuple(t for t in REQUIRED_TABLES if t not in tables)
            if "alembic_version" in tables:
                row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
                status.schema_revision = row[0] if row else None
        finally:
            connection.close()
    except sqlite3.Error as exc:
        log.warning("Could not read database status: %s", exc)
        status.error = "The database file could not be read. It may be corrupted."
    return status


def _copy_database(source: Path, destination: Path) -> None:
    src = sqlite3.connect(str(source))
    try:
        dst = sqlite3.connect(str(destination))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _unused_name(directory: Path, stem: str, suffix: str) -> Path:
    candidate = directory / f"{stem}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def create_backup(db_path: str | Path, backup_dir: str | Path) -> Path:
    """Create a verified backup in ``backup_dir``. Never overwrites an existing file."""
    source = Path(db_path)
    if not source.exists():
        raise BackupError("There is no database to back up yet.")
    directory = Path(backup_dir)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("Cannot create backup directory: %s", exc)
        raise BackupError("The backup folder could not be created or is not writable.") from exc

    target = _unused_name(directory, f"tqi-backup-{datetime.now():%Y%m%d-%H%M%S}", ".db")
    try:
        _copy_database(source, target)
        ok, detail = _integrity(target)
    except (sqlite3.Error, OSError) as exc:
        log.warning("Backup failed: %s", exc)
        target.unlink(missing_ok=True)
        raise BackupError("The backup could not be completed. No valid backup was created.") from exc
    if not ok:
        log.warning("Backup failed integrity check: %s", detail)
        target.unlink(missing_ok=True)
        raise BackupError("The backup failed its integrity check and was discarded.")
    return target


def list_backups(backup_dir: str | Path) -> list[dict]:
    directory = Path(backup_dir)
    if not directory.is_dir():
        return []
    items = []
    for path in sorted(directory.glob("tqi-backup-*.db"), reverse=True):
        stat = path.stat()
        items.append(
            {"name": path.name, "size": stat.st_size, "created": datetime.fromtimestamp(stat.st_mtime)}
        )
    return items


def validate_backup_file(backup_path: str | Path) -> None:
    """Raise ``BackupError`` unless the file is a healthy database containing the app schema."""
    path = Path(backup_path)
    if not path.is_file():
        raise BackupError("The selected backup file does not exist.")
    try:
        ok, detail = _integrity(path)
        if not ok:
            raise BackupError("The backup file failed its integrity check; it was not used.")
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise BackupError("The selected file is not a valid SQLite database.") from exc
    missing = [t for t in REQUIRED_TABLES if t not in tables]
    if missing:
        raise BackupError(
            "The selected file is a database but does not contain the Textile Quality Intelligence "
            f"tables (missing: {', '.join(missing)})."
        )


def restore_backup(backup_path: str | Path, db_path: str | Path) -> Path | None:
    """Replace the active database with a validated backup.

    The current database is first preserved as ``<name>.pre-restore-<timestamp>``. The
    application must be stopped while this runs. Returns the preserved copy (or ``None``
    when there was no existing database).
    """
    backup = Path(backup_path)
    target = Path(db_path)
    validate_backup_file(backup)

    preserved: Path | None = None
    if target.exists():
        preserved = _unused_name(
            target.parent, f"{target.name}.pre-restore-{datetime.now():%Y%m%d-%H%M%S}", ""
        )
        try:
            _copy_database(target, preserved)
        except (sqlite3.Error, OSError) as exc:
            preserved.unlink(missing_ok=True)
            raise BackupError(
                "The current database could not be preserved, so the restore was cancelled."
            ) from exc
    try:
        _copy_database(backup, target)
        ok, detail = _integrity(target)
        if not ok:
            raise BackupError(f"The restored database failed its integrity check ({detail}).")
        connection = sqlite3.connect(str(target))
        try:
            connection.execute("SELECT count(*) FROM inspections").fetchone()
        finally:
            connection.close()
    except (sqlite3.Error, OSError) as exc:
        raise BackupError(
            "The restore did not complete. "
            + (f"Your previous database is preserved as '{preserved.name}'." if preserved else "")
        ) from exc
    return preserved
