"""DefectEntry: one recorded defect finding on an inspection.

A defect entry is a *finding*, not a unique defective product. One garment can have
several entries, so entry counts and quantity sums are reported separately.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.reference_data import utcnow


class DefectEntry(db.Model):
    __tablename__ = "defect_entries"
    __table_args__ = (
        CheckConstraint("defect_quantity > 0", name="ck_defect_entries_quantity_positive"),
        CheckConstraint("length(trim(quantity_unit)) > 0", name="ck_defect_entries_unit"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspection_id: Mapped[int] = mapped_column(
        ForeignKey("inspections.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("defect_categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    severity_id: Mapped[int | None] = mapped_column(
        ForeignKey("severity_levels.id", ondelete="RESTRICT"), index=True
    )
    defect_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(30), nullable=False)
    # A suspected cause is a possible explanation only; NULL means "not recorded".
    suspected_cause: Mapped[str | None] = mapped_column(Text)
    observations: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    inspection = relationship("Inspection", back_populates="defects")
    category = relationship("DefectCategory")
    severity = relationship("SeverityLevel")
    corrective_actions = relationship(
        "CorrectiveAction", back_populates="defect_entry", passive_deletes="all"
    )
