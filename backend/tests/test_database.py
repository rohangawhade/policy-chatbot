from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from adapters.persistence import database, models


async def _employer_row_exists(name: str) -> bool:
    async with database.async_session_factory() as session:
        result = await session.execute(select(models.Employer).where(models.Employer.name == name))
        return result.scalar_one_or_none() is not None


def test_engine_is_async_and_uses_asyncpg_driver() -> None:
    assert isinstance(database.engine, AsyncEngine)
    assert database.engine.dialect.driver == "asyncpg"


def test_session_factory_is_configured_for_async_sessions() -> None:
    assert isinstance(database.async_session_factory, async_sessionmaker)
    assert database.async_session_factory.kw["expire_on_commit"] is False


async def test_get_session_yields_an_async_session() -> None:
    session_gen = database.get_session()
    session = await anext(session_gen)
    try:
        assert isinstance(session, AsyncSession)
    finally:
        await session_gen.aclose()


async def test_get_session_commits_on_a_clean_exit() -> None:
    """Regression test for a real bug (found via Step 9.1's real-stack
    validation of `POST /api/auth/register`): `get_session()` previously
    never committed, so every write through an API route was silently
    discarded the moment the request ended."""
    name = f"commit-test-{uuid4()}"
    try:
        session_gen = database.get_session()
        session = await anext(session_gen)
        session.add(models.Employer(name=name))
        with pytest.raises(StopAsyncIteration):
            await anext(session_gen)

        assert await _employer_row_exists(name)
    finally:
        async with database.async_session_factory() as cleanup_session:
            await cleanup_session.execute(
                delete(models.Employer).where(models.Employer.name == name)
            )
            await cleanup_session.commit()
        # `database.engine`'s pooled connections are bound to the event loop
        # they were opened on. pytest-asyncio gives every test function its
        # own loop, so a connection left in the pool here would be dead
        # (and crash the asyncio proactor) the next time a test reuses it.
        await database.engine.dispose()


async def test_get_session_rolls_back_on_an_exception() -> None:
    name = f"rollback-test-{uuid4()}"
    try:
        session_gen = database.get_session()
        session = await anext(session_gen)
        session.add(models.Employer(name=name))

        with pytest.raises(RuntimeError, match="boom"):
            await session_gen.athrow(RuntimeError("boom"))

        assert not await _employer_row_exists(name)
    finally:
        await database.engine.dispose()
