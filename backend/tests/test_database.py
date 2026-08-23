from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from adapters.persistence import database


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
