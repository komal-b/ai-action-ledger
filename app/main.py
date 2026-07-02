from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.actions import router as actions_router
from app.db.session import engine
from app.db.session import Base
from app.models import action  # noqa: ensures models are registered before create_all
from fastapi.staticfiles import StaticFiles

# Use FastAPI lifespan hooks to run startup/shutdown logic.
# This ensures the database tables are created before the app starts serving requests.
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="AI Action Ledger",
    description="Idempotent, auditable execution log for AI agent actions",
    lifespan=lifespan,
)

# Register the actions API router with the main FastAPI app.
app.include_router(actions_router)


@app.get("/health")
async def health():
    # Simple health check endpoint for readiness and liveness probes.
    return {"status": "ok"}


app.mount("/ui", StaticFiles(directory="app/static", html=True), name="static")
