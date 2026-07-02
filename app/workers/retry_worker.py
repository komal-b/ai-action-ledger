import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.action import Action, AuditEvent
from app.workers.executors import ActionFailed, execute

logger = logging.getLogger(__name__)

POLL_INTERVAL = 30


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _add_audit(session, action_id: uuid.UUID, event_type: str, snapshot: dict) -> None:
    session.add(AuditEvent(action_id=action_id, event_type=event_type, payload_snapshot=snapshot))


async def _process_action(action_id: str) -> None:
    async with AsyncSessionLocal() as session:
        action: Action | None = await session.get(Action, uuid.UUID(action_id))
        if action is None:
            logger.warning("action_id=%s not found in Postgres; skipping", action_id)
            return

        now = datetime.now(timezone.utc)

        if now - _as_utc(action.created_at) > timedelta(hours=24):
            action.status = "dead"
            _add_audit(session, action.id, "dead", {
                "reason": "exceeded_24h_ttl",
                "retry_count": action.retry_count,
            })
            await session.commit()
            logger.warning("action_id=%s → dead (age > 24 h)", action_id)
            return

        try:
            result = await asyncio.to_thread(execute, action.action_type, action.payload)

            action.status = "succeeded"
            action.result = result
            action.executed_at = now
            _add_audit(session, action.id, "succeeded", {
                "result": result,
                "retry_count": action.retry_count,
            })
            await session.commit()
            logger.info("action_id=%s → succeeded (retry=%d)", action_id, action.retry_count)

        except ActionFailed as exc:
            delay_minutes = 2 ** action.retry_count
            action.retry_count += 1
            action.next_retry_at = now + timedelta(minutes=delay_minutes)
            action.error = {"message": str(exc), "retry_count": action.retry_count}
            _add_audit(session, action.id, "failed", {
                "error": str(exc),
                "retry_count": action.retry_count,
                "next_retry_at": action.next_retry_at.isoformat(),
            })
            await session.commit()
            logger.info(
                "action_id=%s → failed (retry=%d, next_retry_at=%s)",
                action_id,
                action.retry_count,
                action.next_retry_at.isoformat(),
            )


async def _poll_loop() -> None:
    while True:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Action).where(
                    Action.status == "failed",
                    Action.next_retry_at <= datetime.now(timezone.utc),
                )
            )
            overdue = result.scalars().all()

        for action in overdue:
            await _process_action(str(action.id))

        await asyncio.sleep(POLL_INTERVAL)


async def run_worker() -> None:
    await _poll_loop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())
