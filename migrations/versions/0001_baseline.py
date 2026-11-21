"""Baseline schema for the enterprise-timeline closed loop.

Revision ID: 0001_baseline
Revises: (none)
DSN is taken from DATABASE_URL at runtime (env only).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

def UUID():
    """Factory: a fresh UUID(as_uuid=True) type instance per column."""
    return postgresql.UUID(as_uuid=True)


def _common_cols():
    return [
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("org_id", UUID(), nullable=False),
        sa.Column("site_id", UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", UUID(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table("enterprise", *_common_cols(),
                    sa.Column("name", sa.String(200), nullable=False))
    for c in ("org_id", "site_id", "deleted_at"):
        op.create_index(f"ix_enterprise_{c}", "enterprise", [c])

    op.create_table("contact", *_common_cols(),
                    sa.Column("enterprise_id", UUID(), nullable=False),
                    sa.Column("name", sa.String(200), nullable=False),
                    sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=True))
    for c in ("org_id", "site_id", "enterprise_id", "deleted_at", "last_interaction_at"):
        op.create_index(f"ix_contact_{c}", "contact", [c])

    op.create_table("member_event", *_common_cols(),
                    sa.Column("title", sa.String(200), nullable=False),
                    sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("ticket_price_cents", sa.Integer(), nullable=False, server_default="0"))
    for c in ("org_id", "site_id", "deleted_at"):
        op.create_index(f"ix_member_event_{c}", "member_event", [c])

    op.create_table("sop_task", *_common_cols(),
                    sa.Column("enterprise_id", UUID(), nullable=False),
                    sa.Column("contact_id", UUID(), nullable=False),
                    sa.Column("code", sa.String(100), nullable=False),
                    sa.Column("status", sa.String(20), nullable=False, server_default="open"),
                    sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
                    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    for c in ("org_id", "site_id", "enterprise_id", "contact_id", "deleted_at"):
        op.create_index(f"ix_sop_task_{c}", "sop_task", [c])

    op.create_table("visit", *_common_cols(),
                    sa.Column("enterprise_id", UUID(), nullable=False),
                    sa.Column("contact_id", UUID(), nullable=False),
                    sa.Column("visit_type", sa.String(50), nullable=False),
                    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("summary", sa.Text(), nullable=False, server_default=""),
                    sa.Column("next_steps", sa.Text(), nullable=False, server_default=""))
    for c in ("org_id", "site_id", "enterprise_id", "contact_id", "occurred_at", "deleted_at"):
        op.create_index(f"ix_visit_{c}", "visit", [c])

    op.create_table("event_checkin", *_common_cols(),
                    sa.Column("enterprise_id", UUID(), nullable=False),
                    sa.Column("contact_id", UUID(), nullable=False),
                    sa.Column("event_id", UUID(), nullable=False),
                    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
    for c in ("org_id", "site_id", "enterprise_id", "contact_id", "event_id", "occurred_at", "deleted_at"):
        op.create_index(f"ix_event_checkin_{c}", "event_checkin", [c])
    op.create_unique_constraint("uq_checkin_contact_event", "event_checkin",
                                ["org_id", "contact_id", "event_id"])

    op.create_table("timeline_event", *_common_cols(),
                    sa.Column("enterprise_id", UUID(), nullable=False),
                    sa.Column("contact_id", UUID(), nullable=False),
                    sa.Column("interaction_type", sa.String(30), nullable=False),
                    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("source_module", sa.String(80), nullable=False),
                    sa.Column("jump_link", sa.Text(), nullable=False),
                    sa.Column("source_ref_id", UUID(), nullable=False),
                    sa.Column("summary", sa.Text(), nullable=False, server_default=""))
    for c in ("org_id", "site_id", "enterprise_id", "contact_id", "interaction_type", "occurred_at", "deleted_at"):
        op.create_index(f"ix_timeline_event_{c}", "timeline_event", [c])
    op.create_unique_constraint("uq_timeline_source", "timeline_event",
                                ["org_id", "interaction_type", "source_ref_id"])


def downgrade() -> None:
    for t in ("timeline_event", "event_checkin", "visit", "sop_task",
              "member_event", "contact", "enterprise"):
        op.drop_table(t)
