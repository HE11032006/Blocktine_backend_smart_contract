"""Add payment_jobs table

Revision ID: 0002_payment_jobs
Revises: 0001_initial
Create Date: 2025-01-02 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_payment_jobs"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payment_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payment_id", sa.String, nullable=False),
        sa.Column("status", sa.String, default="pending"),
        sa.Column("attempts", sa.Integer, default=0),
        sa.Column("max_retries", sa.Integer, default=3),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("next_retry_at", sa.DateTime, nullable=True),
        sa.Column("processed_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_payment_jobs_payment_id", "payment_jobs", ["payment_id"])
    op.create_index("ix_payment_jobs_status", "payment_jobs", ["status"])


def downgrade():
    op.drop_table("payment_jobs")
