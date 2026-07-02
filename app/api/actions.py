import uuid
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.db.session import get_db
from app.models.action import Action, AuditEvent
from app.core.idempotency import claim_action, DuplicateRequest
from app.workers.action_executor import run_action
from app.workers.executors import execute, ActionFailed

# API routes for managing and inspecting recorded actions.
router = APIRouter(prefix="/v1/actions", tags=["actions"])


class CreateActionRequest(BaseModel):
    # Input payload for creating a new action entry.
    actor_id: str
    action_type: str
    payload: dict


def action_to_dict(action: Action) -> dict:
    # Convert an ORM model into a JSON-friendly dictionary for API responses.
    return {
        "id": str(action.id),
        "idempotency_key": action.idempotency_key,
        "actor_id": action.actor_id,
        "action_type": action.action_type,
        "payload": action.payload,
        "status": action.status,
        "result": action.result,
        "error": action.error,
        "created_at": action.created_at.isoformat(),
        "executed_at": action.executed_at.isoformat() if action.executed_at else None,
        }


@router.post("")
async def create_action(
    body: CreateActionRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    # API call: create or reuse an action record based on the idempotency key.
    try:
        action = await claim_action(db, idempotency_key, body.actor_id, body.action_type, body.payload)
    except DuplicateRequest as dup:
        # Key already seen: do NOT re-execute. Return what happened last time.
        return {"duplicate": True, "action": action_to_dict(dup.existing_action)}

    action = await run_action(db, action)
    return {"duplicate": False, "action": action_to_dict(action)}


@router.get("/{action_id}")
async def get_action(action_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    # API call: fetch a single action by its unique identifier.
    result = await db.execute(select(Action).where(Action.id == action_id))
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(404, "action not found")
    return action_to_dict(action)


@router.get("/{action_id}/audit")
async def get_audit(action_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    # API call: return the audit trail for an action in chronological order.
    result = await db.execute(
        select(AuditEvent).where(AuditEvent.action_id == action_id).order_by(AuditEvent.timestamp)
    )
    events = result.scalars().all()
    return [
        {"event_type": e.event_type, "payload_snapshot": e.payload_snapshot, "timestamp": e.timestamp.isoformat()}
        for e in events
    ]


@router.get("")
async def list_actions(actor_id: str | None = None, status: str | None = None, db: AsyncSession = Depends(get_db)):
    # API call: list recent actions, optionally filtered by actor or status.
    q = select(Action)
    if actor_id:
        q = q.where(Action.actor_id == actor_id)
    if status:
        q = q.where(Action.status == status)
    result = await db.execute(q.order_by(Action.created_at.desc()).limit(50))
    return [action_to_dict(a) for a in result.scalars().all()]
