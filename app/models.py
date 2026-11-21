"""SQLAlchemy 2 data model for the enterprise-timeline closed loop.

Conventions (from ticket):
  * every business table carries id(UUID), org_id, site_id, created_at,
    created_by, updated_at, deleted_at (soft delete).
  * monetary values are integers in cents.
  * all data is fictional; no real person or enterprise is represented.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BusinessBase(Base):
    """Abstract base carrying the mandatory common columns."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class Enterprise(BusinessBase):
    __tablename__ = "enterprise"

    name: Mapped[str] = mapped_column(String(200), nullable=False)


class Contact(BusinessBase):
    __tablename__ = "contact"

    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Latest interaction timestamp across all three interaction types.
    last_interaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class MemberEvent(BusinessBase):
    __tablename__ = "member_event"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Ticket price stored as integer cents (convention: amounts are cents).
    ticket_price_cents: Mapped[int] = mapped_column(Integer, default=0)


class SopTask(BusinessBase):
    __tablename__ = "sop_task"

    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), index=True
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Visit(BusinessBase):
    __tablename__ = "visit"

    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), index=True
    )
    visit_type: Mapped[str] = mapped_column(String(50), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    next_steps: Mapped[str] = mapped_column(Text, default="")


class EventCheckin(BusinessBase):
    __tablename__ = "event_checkin"

    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (
        # One check-in per (contact, event): idempotency at the DB layer.
        UniqueConstraint(
            "org_id", "contact_id", "event_id", name="uq_checkin_contact_event"
        ),
    )


class TimelineEvent(BusinessBase):
    """Single consolidated timeline rows; one per interaction across sources."""

    __tablename__ = "timeline_event"

    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), index=True
    )
    interaction_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_module: Mapped[str] = mapped_column(String(80), nullable=False)
    jump_link: Mapped[str] = mapped_column(Text, nullable=False)
    # Primary key of the source record in its own module (stub id in this ticket).
    source_ref_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True))
    summary: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        # Idempotent consolidation: an interaction is written to the timeline once.
        UniqueConstraint(
            "org_id",
            "interaction_type",
            "source_ref_id",
            name="uq_timeline_source",
        ),
    )
