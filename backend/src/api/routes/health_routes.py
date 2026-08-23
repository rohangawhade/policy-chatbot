"""Liveness and readiness probes.

Used by Docker Compose healthchecks (docker-compose.yml) and any future
orchestrator. Kept dependency-light: no repository ports, no domain
services — these routes must work even if the rest of the app is broken.
"""

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from adapters.persistence.database import engine
from config import pinecone_config, redis_config

router = APIRouter(tags=["health"])

DependencyStatus = Literal["ok", "error", "not_configured"]


class ReadinessResponse(BaseModel):
    status: Literal["ok", "error"]
    database: DependencyStatus
    redis: DependencyStatus
    pinecone: DependencyStatus


async def _check_database() -> DependencyStatus:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


async def _check_redis() -> DependencyStatus:
    client = Redis.from_url(redis_config.url)
    try:
        await client.ping()
        return "ok"
    except Exception:
        return "error"
    finally:
        await client.aclose()


async def _check_pinecone() -> DependencyStatus:
    if not pinecone_config.api_key:
        return "not_configured"
    try:
        from pinecone import Pinecone

        def _list_indexes() -> None:
            Pinecone(api_key=pinecone_config.api_key).list_indexes()

        await run_in_threadpool(_list_indexes)
        return "ok"
    except Exception:
        return "error"


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — 200 if the process is up. No dependency checks."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(response: Response) -> ReadinessResponse:
    """Readiness probe — checks PostgreSQL and Redis (required), and
    Pinecone if configured. `not_configured` doesn't count as a failure.
    Returns HTTP 503 (not just an "error" body) when not ready, so
    orchestrators that key off status code behave correctly."""
    database_status = await _check_database()
    redis_status = await _check_redis()
    pinecone_status = await _check_pinecone()

    required_ok = database_status == "ok" and redis_status == "ok"
    pinecone_ok = pinecone_status in ("ok", "not_configured")
    is_ready = required_ok and pinecone_ok

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ok" if is_ready else "error",
        database=database_status,
        redis=redis_status,
        pinecone=pinecone_status,
    )
