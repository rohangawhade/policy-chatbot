from datetime import UTC, datetime, timedelta
from uuid import uuid4

from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.cache.redis_cache_adapter import RedisCacheAdapter
from adapters.event_bus.in_memory_event_bus import InMemoryEventBus
from adapters.llm.litellm_adapter import LiteLLMAdapter
from adapters.persistence.analytics_repo import PostgresAnalyticsRepository
from adapters.persistence.conversation_repo import (
    PostgresConversationRepository,
    PostgresMessageRepository,
)
from adapters.persistence.document_repo import (
    PostgresDocumentChunkRepository,
    PostgresDocumentRepository,
)
from adapters.persistence.employee_repo import PostgresEmployeeRepository
from adapters.persistence.employer_repo import PostgresEmployerRepository
from adapters.persistence.policy_repo import PostgresEnrollmentRepository
from adapters.vector_store.pinecone_adapter import PineconeAdapter
from api.dependencies import (
    get_analytics_repository,
    get_auth_service,
    get_cache_port,
    get_celery_app,
    get_conversation_repository,
    get_document_chunk_repository,
    get_document_repository,
    get_document_service,
    get_employee_repository,
    get_employer_repository,
    get_enrollment_repository,
    get_event_bus,
    get_guardrails_service,
    get_llm_port,
    get_message_repository,
    get_query_router,
    get_rag_service,
    get_vector_store_port,
)
from config import auth_config, llm_config
from core.domain.employee import UserRole
from core.ports.repository_ports import (
    AnalyticsRepository,
    ConversationRepository,
    DocumentChunkRepository,
    DocumentRepository,
    EmployeeRepository,
    EmployerRepository,
    EnrollmentRepository,
    MessageRepository,
)
from core.services.auth_service import AuthService
from core.services.document_service import DocumentService
from core.services.guardrails_service import GuardrailsService
from core.services.query_router import QueryRouter
from core.services.rag_service import RAGService
from workers.celery_app import app as celery_app


def test_get_employee_repository_returns_a_postgres_employee_repository(
    db_session: AsyncSession,
) -> None:
    repository = get_employee_repository(db_session)

    assert isinstance(repository, PostgresEmployeeRepository)
    assert isinstance(repository, EmployeeRepository)


def test_get_employer_repository_returns_a_postgres_employer_repository(
    db_session: AsyncSession,
) -> None:
    repository = get_employer_repository(db_session)

    assert isinstance(repository, PostgresEmployerRepository)
    assert isinstance(repository, EmployerRepository)


def test_get_document_repository_returns_a_postgres_document_repository(
    db_session: AsyncSession,
) -> None:
    repository = get_document_repository(db_session)

    assert isinstance(repository, PostgresDocumentRepository)
    assert isinstance(repository, DocumentRepository)


def test_get_auth_service_wires_the_configured_secret_and_algorithm(
    db_session: AsyncSession,
) -> None:
    repository = get_employee_repository(db_session)

    service = get_auth_service(repository)

    assert isinstance(service, AuthService)
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "employer_id": None,
            "role": UserRole.ADMIN.value,
            "token_type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        auth_config.jwt_secret_key,
        algorithm=auth_config.jwt_algorithm,
    )

    payload = service.decode_token(token)

    assert payload.role == UserRole.ADMIN


def test_get_conversation_repository_returns_a_postgres_conversation_repository(
    db_session: AsyncSession,
) -> None:
    repository = get_conversation_repository(db_session)

    assert isinstance(repository, PostgresConversationRepository)
    assert isinstance(repository, ConversationRepository)


def test_get_message_repository_returns_a_postgres_message_repository(
    db_session: AsyncSession,
) -> None:
    repository = get_message_repository(db_session)

    assert isinstance(repository, PostgresMessageRepository)
    assert isinstance(repository, MessageRepository)


def test_get_enrollment_repository_returns_a_postgres_enrollment_repository(
    db_session: AsyncSession,
) -> None:
    repository = get_enrollment_repository(db_session)

    assert isinstance(repository, PostgresEnrollmentRepository)
    assert isinstance(repository, EnrollmentRepository)


def test_get_analytics_repository_returns_a_postgres_analytics_repository(
    db_session: AsyncSession,
) -> None:
    repository = get_analytics_repository(db_session)

    assert isinstance(repository, PostgresAnalyticsRepository)
    assert isinstance(repository, AnalyticsRepository)


def test_get_llm_port_returns_a_litellm_adapter() -> None:
    assert isinstance(get_llm_port(), LiteLLMAdapter)


def test_get_cache_port_returns_a_redis_cache_adapter() -> None:
    assert isinstance(get_cache_port(), RedisCacheAdapter)


def test_get_vector_store_port_returns_a_pinecone_adapter() -> None:
    assert isinstance(get_vector_store_port(), PineconeAdapter)


def test_get_event_bus_returns_an_in_memory_event_bus() -> None:
    assert isinstance(get_event_bus(), InMemoryEventBus)


def test_get_query_router_wires_the_configured_models() -> None:
    router = get_query_router()

    assert isinstance(router, QueryRouter)
    assert router.select_model(0.0) == llm_config.cheap_model


def test_get_guardrails_service_wires_the_llm_and_event_bus() -> None:
    service = get_guardrails_service(get_llm_port(), get_event_bus())

    assert isinstance(service, GuardrailsService)


def test_get_rag_service_wires_every_collaborator(db_session: AsyncSession) -> None:
    service = get_rag_service(
        get_llm_port(),
        get_cache_port(),
        get_vector_store_port(),
        get_enrollment_repository(db_session),
        get_analytics_repository(db_session),
        get_query_router(),
        get_conversation_repository(db_session),
        get_message_repository(db_session),
        get_event_bus(),
    )

    assert isinstance(service, RAGService)


def test_get_document_chunk_repository_returns_a_postgres_document_chunk_repository(
    db_session: AsyncSession,
) -> None:
    repository = get_document_chunk_repository(db_session)

    assert isinstance(repository, PostgresDocumentChunkRepository)
    assert isinstance(repository, DocumentChunkRepository)


def test_get_document_service_wires_the_repository_and_event_bus(
    db_session: AsyncSession,
) -> None:
    service = get_document_service(get_document_repository(db_session), get_event_bus())

    assert isinstance(service, DocumentService)


def test_get_celery_app_returns_the_shared_celery_app() -> None:
    assert get_celery_app() is celery_app
