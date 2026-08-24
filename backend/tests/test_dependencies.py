from datetime import UTC, datetime, timedelta
from uuid import uuid4

from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.document_repo import PostgresDocumentRepository
from adapters.persistence.employee_repo import PostgresEmployeeRepository
from api.dependencies import get_auth_service, get_document_repository, get_employee_repository
from config import auth_config
from core.domain.employee import UserRole
from core.ports.repository_ports import DocumentRepository, EmployeeRepository
from core.services.auth_service import AuthService


def test_get_employee_repository_returns_a_postgres_employee_repository(
    db_session: AsyncSession,
) -> None:
    repository = get_employee_repository(db_session)

    assert isinstance(repository, PostgresEmployeeRepository)
    assert isinstance(repository, EmployeeRepository)


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
