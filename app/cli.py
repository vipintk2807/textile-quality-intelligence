"""Command-line helpers registered with the ``flask`` command."""

from __future__ import annotations

import click
from flask import Flask

from app.services import data_management_service as dm


def register(app: Flask) -> None:
    @app.cli.command("seed-reference")
    def seed_reference() -> None:
        """Add ILLUSTRATIVE starter defect categories and severity labels (optional)."""
        from app.services.defect_service import seed_illustrative_reference_data

        categories, severities = seed_illustrative_reference_data()
        click.echo(
            f"Added {categories} categories and {severities} severity levels. These are illustrative "
            "examples only - edit them in the application to match your own procedures."
        )

    @app.cli.command("db-status")
    def db_status() -> None:
        """Show the state of the database file."""
        status = dm.database_status(app.config["DATABASE_PATH"])
        click.echo(f"Database file exists : {status.exists}")
        if status.exists:
            click.echo(f"Size (bytes)         : {status.size_bytes}")
            click.echo(f"Integrity check      : {status.integrity_detail or 'not run'}")
            click.echo(f"Schema revision      : {status.schema_revision or 'unknown'}")
            click.echo(f"Missing tables       : {', '.join(status.missing_tables) or 'none'}")
        if status.error:
            click.echo(f"Note                 : {status.error}")

    @app.cli.command("backup")
    def backup() -> None:
        """Create a verified backup in instance/backups."""
        try:
            path = dm.create_backup(app.config["DATABASE_PATH"], app.config["BACKUP_DIR"])
        except dm.BackupError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Verified backup created: {path}")

    @app.cli.command("restore-backup")
    @click.argument("backup_file", type=click.Path(exists=True, dir_okay=False))
    @click.option("--yes", is_flag=True, help="Confirm that the active database may be replaced.")
    def restore_backup(backup_file: str, yes: bool) -> None:
        """Replace the active database with BACKUP_FILE. Stop the application first."""
        click.echo("Restoring REPLACES the current database. Stop the application before continuing.")
        if not yes:
            click.confirm("Do you want to continue?", abort=True)
        try:
            preserved = dm.restore_backup(backup_file, app.config["DATABASE_PATH"])
        except dm.BackupError as exc:
            raise click.ClickException(str(exc)) from exc
        if preserved:
            click.echo(f"Previous database preserved as: {preserved}")
        click.echo("Restore completed and the restored database passed its integrity check.")
