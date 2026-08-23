"""Async SQLAlchemy engine and session factory.

Reads DATABASE_URL directly from the environment for now — Step 1.4 adds
typed configuration (Pydantic Settings), which will supersede this.
"""

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://policypal:policypal@localhost:5432/policypal",
)
DATABASE_POOL_SIZE = int(os.environ.get("DATABASE_POOL_SIZE", "10"))

engine = create_async_engine(DATABASE_URL, pool_size=DATABASE_POOL_SIZE)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped async session."""
    async with async_session_factory() as session:
        yield session
