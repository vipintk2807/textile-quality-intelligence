"""DispositionRecord: outcome of an inspected quantity.

Model chosen for the initial release (technical specification, section 5.6): one
reconciled record per inspection whose four mutually exclusive quantities add up to the
inspected quantity. Cumulative or multi-stage outcomes (for example post-rework
acceptance) are not modelled and need a different design.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.reference_data import utcnow


class DispositionRecord(db.Model):
    __tablename__ = "disposition_records"
    __table_args__ = (
        CheckConstraint("accepted_quantity >= 0", name="ck_disposition_accepted"),
        CheckConstraint("rework_quantity >= 0", name="ck_disposition_rework"),
        CheckConstraint("rejected_quantity >= 0", name="ck_disposition_rejected"),
        CheckConstraint("pending_quantity >= 0", name="ck_disposition_pending"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspection_id: Mapped[int] = mapped_column(
        ForeignKey("inspections.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    accepted_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    rework_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    pending_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(30), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    inspection = relationship("Inspection", back_populates="disposition")

    @property
    def total(self) -> int:
        return (
            self.accepted_quantity
            + self.rework_quantity
            + self.rejected_quantity
            + self.pending_quantity
        )
