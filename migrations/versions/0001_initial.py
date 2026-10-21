"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

STATUSES = ("open", "in_progress", "completed_awaiting_followup", "effective", "not_effective", "closed")
FOLLOWUP_RESULTS = ("effective", "not_effective", "inconclusive")


def _in_list(column, values):
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade():
    op.create_table(
        "defect_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("name_key", sa.String(100), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("name_key"),
    )
    op.create_table(
        "severity_levels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("name_key", sa.String(100), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("name_key"),
    )
    op.create_table(
        "inspections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inspection_code", sa.String(40), nullable=False),
        sa.Column("inspection_date", sa.Date(), nullable=False),
        sa.Column("product_reference", sa.String(120), nullable=False),
        sa.Column("batch_reference", sa.String(120)),
        sa.Column("production_stage", sa.String(80)),
        sa.Column("inspection_type", sa.String(80)),
        sa.Column("inspected_quantity", sa.Integer(), nullable=False),
        sa.Column("quantity_unit", sa.String(30), nullable=False),
        sa.Column("inspector_name", sa.String(120)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("inspection_code"),
        sa.CheckConstraint("inspected_quantity > 0", name="ck_inspections_quantity_positive"),
        sa.CheckConstraint("length(trim(product_reference)) > 0", name="ck_inspections_product"),
        sa.CheckConstraint("length(trim(quantity_unit)) > 0", name="ck_inspections_unit"),
    )
    op.create_index("ix_inspections_inspection_date", "inspections", ["inspection_date"])
    op.create_index("ix_inspections_product_reference", "inspections", ["product_reference"])
    op.create_index("ix_inspections_batch_reference", "inspections", ["batch_reference"])

    op.create_table(
        "defect_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inspection_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("severity_id", sa.Integer()),
        sa.Column("defect_quantity", sa.Integer(), nullable=False),
        sa.Column("quantity_unit", sa.String(30), nullable=False),
        sa.Column("suspected_cause", sa.Text()),
        sa.Column("observations", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["defect_categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["severity_id"], ["severity_levels.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("defect_quantity > 0", name="ck_defect_entries_quantity_positive"),
        sa.CheckConstraint("length(trim(quantity_unit)) > 0", name="ck_defect_entries_unit"),
    )
    op.create_index("ix_defect_entries_inspection_id", "defect_entries", ["inspection_id"])
    op.create_index("ix_defect_entries_category_id", "defect_entries", ["category_id"])
    op.create_index("ix_defect_entries_severity_id", "defect_entries", ["severity_id"])

    op.create_table(
        "disposition_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inspection_id", sa.Integer(), nullable=False),
        sa.Column("accepted_quantity", sa.Integer(), nullable=False),
        sa.Column("rework_quantity", sa.Integer(), nullable=False),
        sa.Column("rejected_quantity", sa.Integer(), nullable=False),
        sa.Column("pending_quantity", sa.Integer(), nullable=False),
        sa.Column("quantity_unit", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("inspection_id"),
        sa.CheckConstraint("accepted_quantity >= 0", name="ck_disposition_accepted"),
        sa.CheckConstraint("rework_quantity >= 0", name="ck_disposition_rework"),
        sa.CheckConstraint("rejected_quantity >= 0", name="ck_disposition_rejected"),
        sa.CheckConstraint("pending_quantity >= 0", name="ck_disposition_pending"),
    )

    op.create_table(
        "corrective_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inspection_id", sa.Integer(), nullable=False),
        sa.Column("defect_entry_id", sa.Integer()),
        sa.Column("problem_description", sa.Text(), nullable=False),
        sa.Column("suspected_cause", sa.Text()),
        sa.Column("confirmed_root_cause", sa.Text()),
        sa.Column("action_description", sa.Text()),
        sa.Column("responsible_person", sa.String(120)),
        sa.Column("target_date", sa.Date()),
        sa.Column("completed_on", sa.Date()),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["defect_entry_id"], ["defect_entries.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(_in_list("status", STATUSES), name="ck_corrective_actions_status"),
        sa.CheckConstraint("length(trim(problem_description)) > 0", name="ck_corrective_actions_problem"),
    )
    op.create_index("ix_corrective_actions_inspection_id", "corrective_actions", ["inspection_id"])
    op.create_index("ix_corrective_actions_defect_entry_id", "corrective_actions", ["defect_entry_id"])
    op.create_index("ix_corrective_actions_target_date", "corrective_actions", ["target_date"])
    op.create_index("ix_corrective_actions_status", "corrective_actions", ["status"])

    op.create_table(
        "action_follow_ups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("corrective_action_id", sa.Integer(), nullable=False),
        sa.Column("follow_up_date", sa.Date(), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("observations", sa.Text(), nullable=False),
        sa.Column("recorded_by", sa.String(120)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["corrective_action_id"], ["corrective_actions.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(_in_list("result", FOLLOWUP_RESULTS), name="ck_follow_ups_result"),
        sa.CheckConstraint("length(trim(observations)) > 0", name="ck_follow_ups_observations"),
    )
    op.create_index("ix_action_follow_ups_corrective_action_id", "action_follow_ups", ["corrective_action_id"])


def downgrade():
    for table in (
        "action_follow_ups",
        "corrective_actions",
        "disposition_records",
        "defect_entries",
        "inspections",
        "severity_levels",
        "defect_categories",
    ):
        op.drop_table(table)
