"""DI wiring: constructs services from ports/adapters for FastAPI's
dependency injection (files/plan.md's api/ folder structure names this
file's exact purpose — "DI: wires ports -> adapters"). `api/` is allowed
to import adapters for this purpose only (files/coding-standards.md
section 3) — no other layer does.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.database import get_session
from adapters.persistence.document_repo import PostgresDocumentRepository
from adapters.persistence.employee_repo import PostgresEmployeeRepository
from config import auth_config
from core.ports.repository_ports import DocumentRepository, EmployeeRepository
from core.services.auth_service import AuthService


def get_employee_repository(session: AsyncSession = Depends(get_session)) -> EmployeeRepository:
    return PostgresEmployeeRepository(session)


def get_document_repository(session: AsyncSession = Depends(get_session)) -> DocumentRepository:
    return PostgresDocumentRepository(session)


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
