"""Pre-import `litellm` with warnings suppressed, and undo its side effect
on `os.environ`.

`litellm` 1.63.x's own import chain triggers several third-party
`DeprecationWarning`s under Python 3.12 (a legacy-`Config`-style pydantic
model, `importlib.resources.open_text`) — none of it our code, all of it
inside `litellm` itself. `pyproject.toml`'s `filterwarnings` turns
`DeprecationWarning` into a hard error (files/coding-standards.md's
zero-deprecation-warnings bar), which would otherwise fail collection the
first time any test imports `litellm`. Importing it once here, before
pytest's warning filters are in effect for individual test modules, means
the module is already in `sys.modules` and re-imports elsewhere are
silent no-ops.

Separately, `litellm/__init__.py` unconditionally calls
`dotenv.load_dotenv()` at import time, which loads the repo-root `.env`
file straight into this process's real `os.environ` — indistinguishable
afterward from a genuinely exported env var, and permanent for the rest
of the process. That defeats every `_env_file=None` isolation in
`test_config.py` (which exists specifically to test config defaults
without this machine's local `.env`) for the rest of the session, the
moment anything imports `litellm`. Undo exactly what it added — any key
that already existed as a real env var is left untouched either way,
since `load_dotenv()` defaults to not overriding existing values.
"""

import os
import warnings
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

_env_before_litellm_import = set(os.environ)

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import litellm  # noqa: F401

for _key in set(os.environ) - _env_before_litellm_import:
    del os.environ[_key]


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A real Postgres-backed session for repository integration tests
    (Step 3.5) — bound to a single connection wrapped in an outer
    transaction that's always rolled back, never committed, so tests
    never persist data or interfere with each other. Repositories only
    ever call `session.flush()`, never `session.commit()` (Unit-of-Work:
    "committed at the API layer" — files/plan.md Step 3.5), so a rollback
    here always fully undoes everything a test did.

    Requires a live Postgres reachable at `DATABASE_URL` (or its default)
    with migrations already applied — `docker compose up -d postgres &&
    alembic upgrade head` locally; `ci.yml`'s `backend-quality` job runs
    a `postgres:16` service and an `alembic upgrade head` step for
    exactly this.
    """
    from config import database_config

    engine = create_async_engine(database_config.url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            # A real DBAPI error (e.g. a constraint-violation test)
            # auto-invalidates the connection's transaction; rolling back
            # an already-deassociated one just emits a harmless SAWarning.
            if connection.in_transaction():
                await transaction.rollback()
    await engine.dispose()
