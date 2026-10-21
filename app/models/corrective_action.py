"""CorrectiveAction and ActionFollowUp.

``completed_on`` is a calendar date entered by the user (never auto-filled), a small
deliberate simplification of the specification's ``completed_at`` timestamp.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.workflow import FOLLOWUP_RESULTS, OPEN, STATUSES
from app.extensions import db
from app.models.reference_data import utcnow


def _in_list(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class CorrectiveAction(db.Model):
    __tablename__ = "corrective_actions"
    __table_args__ = (
        CheckConstraint(_in_list("status", STATUSES), name="ck_corrective_actions_status"),
        CheckConstraint(
            "length(trim(problem_description)) > 0", name="ck_corrective_actions_problem"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspection_id: Mapped[int] = mapped_column(
        ForeignKey("inspections.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    defect_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("defect_entries.id", ondelete="RESTRICT"), index=True
    )
    problem_description: Mapped[str] = mapped_column(Text, nullable=False)
    suspected_cause: Mapped[str | None] = mapped_column(Text)
    confirmed_root_cause: Mapped[str | None] = mapped_column(Text)
    action_description: Mapped[str | None] = mapped_column(Text)
    responsible_person: Mapped[str | None] = mapped_column(String(120))
    target_date: Mapped[date | None] = mapped_column(Date, index=True)
    completed_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default=OPEN, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    inspection = relationship("Inspection", back_populates="corrective_actions")
    defect_entry = relationship("DefectEntry", back_populates="corrective_actions")
    follow_ups = relationship(
        "ActionFollowUp",
        back_populates="corrective_action",
        order_by="ActionFollowUp.follow_up_date, ActionFollowUp.id",
        passive_deletes="all",
    )


class ActionFollowUp(db.Model):
    """One effectiveness assessment. Earlier assessments are kept as history."""

    __tablename__ = "action_follow_ups"
    __table_args__ = (
        CheckConstraint(_in_list("result", FOLLOWUP_RESULTS), name="ck_follow_ups_result"),
        CheckConstraint("length(trim(observations)) > 0", name="ck_follow_ups_observations"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    corrective_action_id: Mapped[int] = mapped_column(
        ForeignKey("corrective_actions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    follow_up_date: Mapped[date] = mapped_column(Date, nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    observations: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_by: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    corrective_action = relationship("CorrectiveAction", back_populates="follow_ups")
