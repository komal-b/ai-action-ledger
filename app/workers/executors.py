"""
Mock 'real world' side effects so we can prove idempotency actually works,
by checking these in-memory stores stay correct under duplicate requests.
In production these would be real calls: booking system, payment processor, etc.
"""
import random

# in-memory fake external state, just for demo purposes
fake_appointments: list[dict] = []
fake_messages_sent: list[dict] = []
fake_claims: list[dict] = []


class ActionFailed(Exception):
    pass


def execute_book_appointment(payload: dict) -> dict:
    fake_appointments.append(payload)
    return {"status": "booked", "appointment_index": len(fake_appointments) - 1}


def execute_send_payment_reminder(payload: dict) -> dict:
    fake_messages_sent.append(payload)
    return {"status": "sent", "message_index": len(fake_messages_sent) - 1}


def execute_submit_claim(payload: dict) -> dict:
    if random.random() < 1.0:
        raise ActionFailed("simulated payer system timeout")
    fake_claims.append(payload)
    return {"status": "submitted", "claim_index": len(fake_claims) - 1}


EXECUTORS = {
    "book_appointment": execute_book_appointment,
    "send_payment_reminder": execute_send_payment_reminder,
    "submit_claim": execute_submit_claim,
}


def execute(action_type: str, payload: dict) -> dict:
    handler = EXECUTORS.get(action_type)
    if handler is None:
        raise ActionFailed(f"unknown action_type: {action_type}")
    return handler(payload)
