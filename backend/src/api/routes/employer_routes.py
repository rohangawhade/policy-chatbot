"""Employer (tenant) CRUD — admin only (files/plan.md Step 9.4).

Response shape matches the established convention from Step 9.1 (see
`auth_routes.py`'s module docstring) — this file returns its Pydantic
model(s) directly, not wrapped in `files/coding-standards.md` section
7's `APIResponse[T]` envelope.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from api.dependencies import get_employer_repository
from api.middleware.auth_middleware import require_role
from core.domain.employee import UserRole
from core.domain.employer import Employer
from core.domain.errors import NotFoundError
from core.ports.repository_ports import EmployerRepository

router = APIRouter(
    prefix="/api/employers",
    tags=["employers"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)


class EmployerResponse(BaseModel):
    id: UUID
    name: str
    is_active: bool


class EmployerCreateRequest(BaseModel):
    name: str


class EmployerUpdateRequest(BaseModel):
    name: str | None = None
    is_active: bool | None = None


def _to_response(employer: Employer) -> EmployerResponse:
    return EmployerResponse(id=employer.id, name=employer.name, is_active=employer.is_active)


async def _get_employer_or_404(
    employer_repository: EmployerRepository, employer_id: UUID
) -> Employer:
    employer = await employer_repository.get(employer_id)
    if employer is None:
        raise NotFoundError("Employer not found.", code="not_found")
    return employer


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_employer(
    body: EmployerCreateRequest,
    employer_repository: EmployerRepository = Depends(get_employer_repository),
) -> EmployerResponse:
    created = await employer_repository.create(Employer(name=body.name))
    return _to_response(created)


@router.get("")
async def list_employers(
    employer_repository: EmployerRepository = Depends(get_employer_repository),
) -> list[EmployerResponse]:
    employers = await employer_repository.list_all()
    return [_to_response(employer) for employer in employers]


@router.get("/{employer_id}")
async def get_employer(
    employer_id: UUID,
    employer_repository: EmployerRepository = Depends(get_employer_repository),
) -> EmployerResponse:
    employer = await _get_employer_or_404(employer_repository, employer_id)
    return _to_response(employer)


@router.patch("/{employer_id}")
async def update_employer(
    employer_id: UUID,
    body: EmployerUpdateRequest,
    employer_repository: EmployerRepository = Depends(get_employer_repository),
) -> EmployerResponse:
    employer = await _get_employer_or_404(employer_repository, employer_id)
    updated = await employer_repository.update(
        employer.model_copy(update=body.model_dump(exclude_unset=True))
    )
    return _to_response(updated)


@router.delete("/{employer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employer(
    employer_id: UUID,
    employer_repository: EmployerRepository = Depends(get_employer_repository),
) -> None:
    await _get_employer_or_404(employer_repository, employer_id)
    await employer_repository.delete(employer_id)
