from sqlalchemy.ext.asyncio import AsyncSession
from app.models.action import Action, AuditEvent
from app.workers.executors import execute, ActionFailed
from datetime import datetime, timedelta, timezone


async def run_action(db: AsyncSession, action: Action) -> Action:
    action.status = "executing"
    db.add(AuditEvent(action_id=action.id, event_type="executing", payload_snapshot={}))
    await db.commit()

    try:
        result = execute(action.action_type, action.payload)
        action.status = "succeeded"
        action.result = result
        db.add(AuditEvent(action_id=action.id, event_type="succeeded", payload_snapshot={"result": result}))

        
    except ActionFailed as e:
        action.status = "failed"
        action.error = {"message": str(e)}
        action.retry_count += 1
        action.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=2 ** action.retry_count)  # Exponential backoff: 2, 4, 8, ...
        db.add(AuditEvent(action_id=action.id, event_type="failed", payload_snapshot={"error": str(e)}))
    await db.commit()
    await db.refresh(action)
    return action
