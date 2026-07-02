"""
Core idempotency logic.

The critical invariant: claim the key BEFORE doing any work, using a DB-level
unique constraint to resolve races atomically. We never check-then-write in
two separate steps without a constraint backing it up, because two concurrent
requests could both pass the check before either writes.
"""
import uuid
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.action import Action, AuditEvent


class DuplicateRequest(Exception):
    """Raised when an idempotency key already exists. Caller should fetch and return the existing action."""
    def __init__(self, existing_action: Action):
        self.existing_action = existing_action


async def claim_action(
    db: AsyncSession,
    idempotency_key: str,
    actor_id: str,
    action_type: str,
    payload: dict,
) -> Action:
    """
    Attempt to atomically claim an idempotency key by inserting a new Action row.
    If the key already exists, raises DuplicateRequest with the existing row instead
    of creating a duplicate or re-executing anything.
    """
    action = Action(
        id=uuid.uuid4(),
        idempotency_key=idempotency_key,
        actor_id=actor_id,
        action_type=action_type,
        payload=payload,
        status="pending",
    )
    db.add(action)
    try:
        await db.flush()  # triggers the unique constraint check without committing yet
    except IntegrityError:
        await db.rollback()
        result = await db.execute(select(Action).where(Action.idempotency_key == idempotency_key))
        existing = result.scalar_one()
        raise DuplicateRequest(existing)

    db.add(AuditEvent(action_id=action.id, event_type="created", payload_snapshot={"payload": payload}))
    await db.commit()
    await db.refresh(action)
    return action
