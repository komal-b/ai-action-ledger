import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# Database connection URL can be overridden by the environment.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://ledger:ledger@localhost:5432/ledger",
)

# Create an async SQLAlchemy engine for PostgreSQL.
engine = create_async_engine(DATABASE_URL, echo=False)

# Configure an async session factory.
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    # Base class for SQLAlchemy ORM models.
    pass


async def get_db():
    # Dependency for FastAPI endpoints that yields a database session.
    async with AsyncSessionLocal() as session:
        yield session
