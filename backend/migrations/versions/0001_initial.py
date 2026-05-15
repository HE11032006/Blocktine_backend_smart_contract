"""Initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone_number", sa.String, unique=True, nullable=False),
        sa.Column("full_name", sa.String, nullable=False),
        sa.Column("supabase_auth_id", sa.String, unique=True, nullable=True),
        sa.Column("wallet_address", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("amount_fcfa", sa.Integer, nullable=False),
        sa.Column("frequency_days", sa.Integer, nullable=False),
        sa.Column("max_members", sa.Integer, nullable=False),
        sa.Column("current_round", sa.Integer, default=0),
        sa.Column("start_date", sa.DateTime, nullable=True),
        sa.Column("is_public", sa.Boolean, default=False),
        sa.Column("invite_code", sa.String, unique=True, nullable=True),
        sa.Column("creator_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("contract_group_id", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reception_rank", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("joined_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "rounds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("round_number", sa.Integer, nullable=False),
        sa.Column("winner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("scheduled_date", sa.DateTime, nullable=False),
        sa.Column("status", sa.String, default="pending"),
        sa.Column("tx_hash_distribute", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("round_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rounds.id"), nullable=False),
        sa.Column("amount_fcfa", sa.Integer, nullable=False),
        sa.Column("amount_usdc", sa.Numeric(18, 6), nullable=True),
        sa.Column("tx_hash", sa.String, nullable=True),
        sa.Column("flutterwave_ref", sa.String, unique=True, nullable=True),
        sa.Column("status", sa.String, default="pending"),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("confirmed_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "webhook_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String, nullable=False),
        sa.Column("idempotency_key", sa.String, unique=True, nullable=False),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("received_at", sa.DateTime, nullable=True),
        sa.Column("processed", sa.Boolean, default=False),
    )

    op.create_index("ix_users_phone_number", "users", ["phone_number"])
    op.create_index("ix_webhook_logs_idempotency_key", "webhook_logs", ["idempotency_key"])


def downgrade():
    op.drop_table("webhook_logs")
    op.drop_table("payments")
    op.drop_table("rounds")
    op.drop_table("members")
    op.drop_table("groups")
    op.drop_table("users")
