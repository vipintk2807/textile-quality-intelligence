from __future__ import annotations

from flask import Blueprint, current_app, redirect, render_template, url_for

from app.routes._helpers import ok, warn
from app.services import data_management_service as dm

bp = Blueprint("data", __name__, url_prefix="/data")


@bp.get("/")
def index():
    db_path = current_app.config["DATABASE_PATH"]
    return render_template(
        "data_management/index.html",
        status=dm.database_status(db_path),
        db_path=str(db_path),
        backup_dir=str(current_app.config["BACKUP_DIR"]),
        backups=dm.list_backups(current_app.config["BACKUP_DIR"]),
    )


@bp.post("/backup")
def backup():
    try:
        path = dm.create_backup(current_app.config["DATABASE_PATH"], current_app.config["BACKUP_DIR"])
    except dm.BackupError as exc:
        warn(str(exc))
    else:
        ok(f"Verified backup created: {path.name}")
    return redirect(url_for("data.index"))
