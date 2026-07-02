import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow():
    return datetime.now(timezone.utc)


class Action(Base):
    __tablename__ = "actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    actor_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    action_type: Mapped[str] = mapped_column(String, index=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)  # pending|executing|succeeded|failed|dead
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="action", order_by="AuditEvent.timestamp")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actions.id"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)  # created|queued|executing|succeeded|failed|replayed
    payload_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    action: Mapped["Action"] = relationship(back_populates="audit_events")


Index("ix_actions_actor_status", Action.actor_id, Action.status)
