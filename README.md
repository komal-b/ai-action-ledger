# AI Action Ledger

![Python](https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?style=flat-square&logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue?style=flat-square&logo=postgresql)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker)

> **Idempotent, auditable execution log for AI agent actions.**

---

## What this is

AI Action Ledger is a backend infrastructure layer that solves a specific problem with AI agents: when an agent takes a real-world action (booking an appointment, submitting a claim, sending a payment reminder), network timeouts and automatic retries can cause that action to execute twice. Most early-stage AI products don't handle this until it causes a production incident.

This project provides:
- **Idempotency** - every agent action executes exactly once, no matter how many times it's retried
- **Audit log** - append-only, tamper-evident record of every action and state transition
- **Automatic retry** - failed actions are retried with exponential backoff, moved to dead state after 24 hours
- **Live dashboard** - UI to submit actions, inspect status, and view full audit trails

---

## Why duplicate execution happens

AI agents retry automatically. When an agent calls a tool (book appointment, submit claim) and the network times out, the agent framework retries the request — even if the first call already succeeded on the server side. The server receives two requests for the same logical action.

Without idempotency:
```
Agent sends request → network timeout → agent retries
Server received BOTH requests → action executes twice
Patient gets double-booked. Debtor gets double-charged.
```

With AI Action Ledger:
```
Agent sends request with Idempotency-Key → network timeout → agent retries same key
Server sees key already exists → returns cached result → action executes once
```

The key mechanism: PostgreSQL's unique constraint on the idempotency key claims the action atomically before any execution happens. Two simultaneous requests for the same key, only one wins, the other gets the cached result.

---

## Architecture

```
Agent / Client
     │
     ▼
POST /v1/actions (Idempotency-Key header)
     │
     ├── Key seen before? → return cached result (no re-execution)
     │
     └── New key → claim atomically in Postgres
                 → execute action (book, claim, reminder)
                 → write result + audit events
                 → return result

Background Worker (runs independently)
     │
     └── polls Postgres every 30s for status=failed AND next_retry_at <= now
               │
               ├── created_at > 24h → status=dead, notify
               │
               └── retry with exponential backoff (2^retry_count minutes)
```

---

## Tech stack

| Tool | Why |
|------|-----|
| **FastAPI** | Async Python API framework, type-safe, fast to build |
| **PostgreSQL** | Source of truth, unique constraint enforces idempotency atomically |
| **SQLAlchemy (async)** | ORM with async session support for FastAPI |
| **Docker Compose** | Runs app + worker + postgres as isolated services |
| **HTML/CSS/JS** | Single-file dashboard, no build step needed |

---

## How to run

**Prerequisites:** Docker Desktop running

```bash
git clone https://github.com/komal-b/ai-action-ledger.git
cd ai-action-ledger
docker compose up --build
```

That's it. Three services start:
- `app` → API at http://localhost:8000
- `worker` → retry worker polling Postgres every 30s
- `postgres` → database, tables auto-created on startup

**Open the dashboard:**
```
http://localhost:8000/ui
```

---

## API endpoints

### Submit an action
```bash
curl -X POST http://localhost:8000/v1/actions \
  -H "Idempotency-Key: book-patient123-july1-10am" \
  -H "Content-Type: application/json" \
  -d '{
    "actor_id": "prosper-agent-1",
    "action_type": "book_appointment",
    "payload": {"patient_id": "p123", "slot": "2026-07-01T10:00"}
  }'
```

### Get action status
```bash
curl http://localhost:8000/v1/actions/{action_id}
```

### Get full audit trail
```bash
curl http://localhost:8000/v1/actions/{action_id}/audit
```

### Replay action (dry run)
```bash
curl -X POST http://localhost:8000/v1/actions/{action_id}/replay
```

### List actions
```bash
curl "http://localhost:8000/v1/actions?actor_id=prosper-agent-1&status=failed"
```

**Supported action types:** `book_appointment` · `send_payment_reminder` · `submit_claim`

---

## Testing idempotency

Send the same request twice with the same `Idempotency-Key`:

```bash
# First request — executes the action
curl -X POST http://localhost:8000/v1/actions \
  -H "Idempotency-Key: test-001" \
  -H "Content-Type: application/json" \
  -d '{"actor_id":"agent-1","action_type":"book_appointment","payload":{"patient_id":"p123","slot":"2026-07-01T10:00"}}'

# Same request again — returns cached result, no re-execution
curl -X POST http://localhost:8000/v1/actions \
  -H "Idempotency-Key: test-001" \
  -H "Content-Type: application/json" \
  -d '{"actor_id":"agent-1","action_type":"book_appointment","payload":{"patient_id":"p123","slot":"2026-07-01T10:00"}}'
```

**What to look for:**
- First response: `"duplicate": false` — action executed
- Second response: `"duplicate": true` — same `id` returned, action did NOT run again

---

## Retry worker behavior

When an action fails:

```
Failure → retry_count=1, next_retry_at=now+2min  (2^1)
Retry fails → retry_count=2, next_retry_at=now+4min  (2^2)
Retry fails → retry_count=3, next_retry_at=now+8min  (2^3)
...
After 24 hours → status=dead, notify agent to retry with new key
```

Worker always writes to Postgres before doing anything else — Postgres is the source of truth, not an in-memory queue.

---

## What's next

This was built as a focused 1-hour project to demonstrate the core pattern. Production extensions:

- **Observability** - OpenTelemetry tracing across the full action lifecycle so you can see exactly where time is spent per action
- **Agent analytics** - track which agents produce the most failures, which action types have the highest retry rates, and whether the system needs additional infrastructure (Redis queue, Kafka) at higher volume
- **Cryptographic audit signing** - sign each audit event so the trail is verifiably untampered (relevant for insurance/healthcare compliance)
- **Webhook delivery** - replace mock executors with real outbound webhook calls to external systems, with the same idempotency guarantees
- **Kubernetes-ready** - worker is stateless and externally configured, horizontal scaling is straightforward

---

## Engineering concepts demonstrated

- Idempotency keys and exactly-once execution semantics
- Optimistic concurrency with database-level unique constraints
- `flush()` vs `commit()` — why the order prevents race conditions
- Append-only audit logging as a compliance pattern
- Event sourcing — state derived from an immutable event log
- Background worker separation from API process
- Exponential backoff and dead letter handling
