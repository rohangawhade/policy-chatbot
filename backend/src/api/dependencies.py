"""DI wiring: constructs services from ports/adapters for FastAPI's
dependency injection (files/plan.md's api/ folder structure names this
file's exact purpose — "DI: wires ports -> adapters"). `api/` is allowed
to import adapters for this purpose only (files/coding-standards.md
section 3) — no other layer does.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.cache.redis_cache_adapter import RedisCacheAdapter
from adapters.event_bus.in_memory_event_bus import InMemoryEventBus
from adapters.llm.litellm_adapter import LiteLLMAdapter
from adapters.persistence.analytics_repo import PostgresAnalyticsRepository
from adapters.persistence.conversation_repo import (
    PostgresConversationRepository,
    PostgresMessageRepository,
)
from adapters.persistence.database import get_session
from adapters.persistence.document_repo import PostgresDocumentRepository
from adapters.persistence.employee_repo import PostgresEmployeeRepository
from adapters.persistence.employer_repo import PostgresEmployerRepository
from adapters.persistence.policy_repo import PostgresEnrollmentRepository
from adapters.vector_store.pinecone_adapter import PineconeAdapter
from config import auth_config, llm_config, pinecone_config, redis_config
from core.ports.cache_port import CachePort
from core.ports.event_bus_port import EventBusPort
from core.ports.llm_port import LLMPort
from core.ports.repository_ports import (
    AnalyticsRepository,
    ConversationRepository,
    DocumentRepository,
    EmployeeRepository,
    EmployerRepository,
    EnrollmentRepository,
    MessageRepository,
)
from core.ports.vector_store_port import VectorStorePort
from core.services.auth_service import AuthService
from core.services.guardrails_service import GuardrailsService
from core.services.query_router import QueryRouter
from core.services.rag_service import RAGService


def get_employee_repository(session: AsyncSession = Depends(get_session)) -> EmployeeRepository:
    return PostgresEmployeeRepository(session)


def get_employer_repository(session: AsyncSession = Depends(get_session)) -> EmployerRepository:
    return PostgresEmployerRepository(session)


def get_document_repository(session: AsyncSession = Depends(get_session)) -> DocumentRepository:
    return PostgresDocumentRepository(session)


def get_conversation_repository(
    session: AsyncSession = Depends(get_session),
) -> ConversationRepository:
    return PostgresConversationRepository(session)


def get_message_repository(session: AsyncSession = Depends(get_session)) -> MessageRepository:
    return PostgresMessageRepository(session)


def get_enrollment_repository(
    session: AsyncSession = Depends(get_session),
) -> EnrollmentRepository:
    return PostgresEnrollmentRepository(session)


def get_analytics_repository(
    session: AsyncSession = Depends(get_session),
) -> AnalyticsRepository:
    return PostgresAnalyticsRepository(session)


def get_auth_service(
    employee_repository: EmployeeRepository = Depends(get_employee_repository),
) -> AuthService:
    return AuthService(
        employee_repository,
        secret_key=auth_config.jwt_secret_key,
        algorithm=auth_config.jwt_algorithm,
        access_token_expire_minutes=auth_config.access_token_expire_minutes,
        refresh_token_expire_days=auth_config.refresh_token_expire_days,
    )


def get_llm_port() -> LLMPort:
    return LiteLLMAdapter()


def get_cache_port() -> CachePort:
    return RedisCacheAdapter(url=redis_config.url)


def get_vector_store_port() -> VectorStorePort:
    # A placeholder, not "" — the Pinecone SDK treats an empty string as
    # falsy and falls through to reading the PINECONE_API_KEY env var
    # itself; with neither set, it raises PineconeConfigurationError at
    # *construction*, before any real call. Found via Step 9.2's own
    # test suite (this dev/CI environment has no real Pinecone key,
    # Steps 3.2/3.3's note) — `workers/embedding_task.py`/
    # `document_ingestion_task.py`'s matching `... or ""` had the same
    # latent bug, fixed alongside this.
    return PineconeAdapter(
        api_key=pinecone_config.api_key or "unconfigured", index_name=pinecone_config.index_name
    )


def get_event_bus() -> EventBusPort:
    # A fresh instance per request, not a shared singleton — matches
    # every Celery task's existing wiring (`embedding_task.py`,
    # `document_ingestion_task.py`). No subscriber-registration
    # infrastructure exists anywhere in the app yet (a standing gap
    # tracked in IMPLEMENTATION_STATUS.md since Step 6.1) — a shared
    # instance would have nothing to make it more useful than a fresh one
    # until that's built.
    return InMemoryEventBus()


def get_query_router() -> QueryRouter:
    return QueryRouter(
        cheap_model=llm_config.cheap_model,
        powerful_model=llm_config.powerful_model,
        complexity_threshold=llm_config.complexity_threshold,
    )


def get_guardrails_service(
    llm: LLMPort = Depends(get_llm_port),
    event_bus: EventBusPort = Depends(get_event_bus),
) -> GuardrailsService:
    return GuardrailsService(llm, event_bus, cheap_model=llm_config.cheap_model)


def get_rag_service(
    llm: LLMPort = Depends(get_llm_port),
    cache: CachePort = Depends(get_cache_port),
    vector_store: VectorStorePort = Depends(get_vector_store_port),
    enrollment_repository: EnrollmentRepository = Depends(get_enrollment_repository),
    analytics_repository: AnalyticsRepository = Depends(get_analytics_repository),
    query_router: QueryRouter = Depends(get_query_router),
    conversation_repository: ConversationRepository = Depends(get_conversation_repository),
    message_repository: MessageRepository = Depends(get_message_repository),
    event_bus: EventBusPort = Depends(get_event_bus),
) -> RAGService:
    return RAGService(
        llm,
        cache,
        vector_store,
        enrollment_repository,
        analytics_repository,
        query_router,
        conversation_repository,
        message_repository,
        event_bus,
        embedding_model=llm_config.embedding_model,
    )
