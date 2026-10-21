"""Centralised configuration.

Settings come from environment variables with safe defaults for local use.
The database path is always resolved relative to the project folder, never the
current working directory.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"
DEFAULT_DB_NAME = "textile_quality.db"
VALID_ENVIRONMENTS = {"development", "production", "testing"}


def resolve_database_path(raw: str | None = None) -> Path:
    """Return the absolute SQLite file path.

    A relative TQI_DATABASE_PATH is resolved against the project folder.
    """
    if raw and raw.strip():
        path = Path(raw.strip()).expanduser()
        if not path.is_absolute():
            path = BASE_DIR / path
        return path.resolve()
    return (INSTANCE_DIR / DEFAULT_DB_NAME).resolve()


def _local_secret_key() -> str:
    """Create (once) and reuse a random development secret key stored in instance/."""
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    key_file = INSTANCE_DIR / ".secret_key"
    if key_file.exists():
        value = key_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_hex(32)
    key_file.write_text(value, encoding="utf-8")
    return value


def load_config(env_name: str | None = None) -> dict:
    """Build the Flask configuration dictionary from the environment."""
    env = (env_name or os.environ.get("TQI_ENV", "development")).strip().lower()
    if env not in VALID_ENVIRONMENTS:
        raise RuntimeError(
            f"Unknown TQI_ENV '{env}'. Use one of: {', '.join(sorted(VALID_ENVIRONMENTS))}."
        )

    secret = os.environ.get("TQI_SECRET_KEY", "").strip()
    if not secret:
        if env == "production":
            raise RuntimeError(
                "TQI_SECRET_KEY must be set when TQI_ENV=production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        secret = _local_secret_key()

    db_path = resolve_database_path(os.environ.get("TQI_DATABASE_PATH"))
    debug = env == "development" and os.environ.get("TQI_DEBUG", "0") == "1"

    return {
        "TQI_ENV": env,
        "SECRET_KEY": secret,
        "DEBUG": debug,
        "TESTING": env == "testing",
        "DATABASE_PATH": str(db_path),
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path.as_posix()}",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "LOG_LEVEL": os.environ.get("TQI_LOG_LEVEL", "INFO").upper(),
        "BACKUP_DIR": str(INSTANCE_DIR / "backups"),
        "PAGE_SIZE": 25,
        "MAX_DEFECTS_PER_FORM": 50,
        "MAX_CONTENT_LENGTH": 1024 * 1024,
        "WTF_CSRF_ENABLED": True,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
    }
