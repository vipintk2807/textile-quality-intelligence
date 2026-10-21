"""Configurable reference data: defect categories and severity levels."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


def utcnow() -> datetime:
    """Naive UTC timestamp (all stored timestamps are UTC)."""

    return datetime.now(UTC).replace(tzinfo=None)


class DefectCategory(db.Model):
    """A defect classification. Deactivate rather than delete once it has been used."""

    __tablename__ = "defect_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Lower-cased, trimmed copy of name: enforces case-insensitive uniqueness in the database.
    name_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class SeverityLevel(db.Model):
    """A deployment-defined severity label. It carries no built-in acceptance rule."""

    __tablename__ = "severity_levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
