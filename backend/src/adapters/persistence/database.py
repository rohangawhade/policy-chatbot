"""Async SQLAlchemy engine and session factory."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import database_config

engine = create_async_engine(database_config.url, pool_size=database_config.pool_size)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped async session.

    Commits once the route handler returns cleanly, rolls back if it
    raised — "a single session per request, committed at the API layer"
    (files/plan.md Step 3.5's Unit-of-Work contract; repositories
    themselves only ever `flush()`, never `commit()`). Nothing enforced
    this until now: every route before Step 9.1 was read-only, so an
    uncommitted-then-discarded transaction was never visible. Found via
    real-stack validation of `POST /api/auth/register` — a second
    registration with the same email returned 201 instead of 409 because
    the first request's insert was flushed (visible within its own
    transaction) but silently rolled back when that request's session
    closed uncommitted.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
