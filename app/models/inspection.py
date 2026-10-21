"""Inspection: one recorded inspection event."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.reference_data import utcnow


class Inspection(db.Model):
    __tablename__ = "inspections"
    __table_args__ = (
        CheckConstraint("inspected_quantity > 0", name="ck_inspections_quantity_positive"),
        CheckConstraint("length(trim(product_reference)) > 0", name="ck_inspections_product"),
        CheckConstraint("length(trim(quantity_unit)) > 0", name="ck_inspections_unit"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspection_code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    inspection_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    product_reference: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    batch_reference: Mapped[str | None] = mapped_column(String(120), index=True)
    production_stage: Mapped[str | None] = mapped_column(String(80))
    inspection_type: Mapped[str | None] = mapped_column(String(80))
    inspected_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(30), nullable=False)
    inspector_name: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    # No ORM cascade: the database foreign keys use RESTRICT so history is never
    # deleted silently. The service layer checks dependencies before any delete.
    defects = relationship(
        "DefectEntry",
        back_populates="inspection",
        order_by="DefectEntry.id",
        passive_deletes="all",
    )
    disposition = relationship(
        "DispositionRecord",
        back_populates="inspection",
        uselist=False,
        passive_deletes="all",
    )
    corrective_actions = relationship(
        "CorrectiveAction",
        back_populates="inspection",
        order_by="CorrectiveAction.id",
        passive_deletes="all",
    )
