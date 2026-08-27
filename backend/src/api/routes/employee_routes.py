"""Employee CRUD under an employer, plus the employee's own enrolled
policies (files/plan.md Step 9.4).

Response shape matches the established convention from Step 9.1 (see
`auth_routes.py`'s module docstring) — this file returns its Pydantic
model(s) directly, not wrapped in `files/coding-standards.md` section
7's `APIResponse[T]` envelope.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.dependencies import (
    get_employee_repository,
    get_enrollment_repository,
    get_policy_repository,
)
from api.middleware.auth_middleware import get_current_user, require_role
from api.middleware.tenant_context import get_current_employer_id
from core.domain.employee import Employee, UserRole
from core.domain.errors import NotFoundError
from core.domain.policy import PolicyType
from core.ports.repository_ports import (
    EmployeeRepository,
    EnrollmentRepository,
    PolicyRepository,
)
from core.services.auth_service import AuthService, TokenPayload

router = APIRouter(prefix="/api/employees", tags=["employees"])

# Only these two roles are creatable through this management endpoint —
# same restriction, and the same reasoning, as auth_routes.py's
# self-registration: ADMIN is a superuser scoped to no employer, created
# out-of-band, never through an employer-scoped CRUD surface. Employee
# *management* (list/view/update/deactivate) is deliberately restricted
# to EMPLOYER/ADMIN callers below — this is PII (email, full name), a
# stricter default than Step 9.3's employer-wide document list.
_SELF_REGISTERABLE_ROLES = (UserRole.EMPLOYER, UserRole.EMPLOYEE)

_require_manager = require_role(UserRole.EMPLOYER, UserRole.ADMIN)


class EmployeeResponse(BaseModel):
    id: UUID
    employer_id: UUID | None
    email: str
    full_name: str
    role: UserRole
    is_active: bool


class EmployeeCreateRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: UserRole
    employer_id: UUID | None = None


class EmployeeUpdateRequest(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None


class EnrolledPolicyResponse(BaseModel):
    policy_id: UUID
    name: str
    policy_type: PolicyType
    is_active: bool


def _to_response(employee: Employee) -> EmployeeResponse:
    return EmployeeResponse(
        id=employee.id,
        employer_id=employee.employer_id,
        email=employee.email,
        full_name=employee.full_name,
        role=employee.role,
        is_active=employee.is_active,
    )


def _resolve_target_employer_id(current_user: TokenPayload, employer_id_field: UUID | None) -> UUID:
    """Same pattern as `document_routes.py`'s upload route: an
    `EMPLOYER` always acts under their own token-derived `employer_id`;
    an `ADMIN` (none of its own) must name one explicitly."""
    if current_user.employer_id is not None:
        return current_user.employer_id
    if employer_id_field is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="employer_id is required when acting as an admin account.",
        )
    return employer_id_field


async def _get_managed_employee(
    employee_repository: EmployeeRepository, employee_id: UUID, current_user: TokenPayload
) -> Employee:
    """Same not-found-vs-forbidden reasoning as `document_routes.py`'s
    ownership checks — an `ADMIN` may manage any employer's employees."""
    employee = await employee_repository.get(employee_id)
    if employee is None:
        raise NotFoundError("Employee not found.", code="not_found")
    if current_user.role != UserRole.ADMIN and employee.employer_id != current_user.employer_id:
        raise NotFoundError("Employee not found.", code="not_found")
    return employee


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_require_manager)])
async def create_employee(
    body: EmployeeCreateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    employee_repository: EmployeeRepository = Depends(get_employee_repository),
) -> EmployeeResponse:
    """Create an employee (or employer-contact) account under an
    employer. Unlike `POST /api/auth/register`, this is initiated by an
    `EMPLOYER`/`ADMIN` on someone else's behalf, not self-service, and
    doesn't return tokens — the new account logs in separately.

    Raises:
        HTTPException: 422 if `role` is `ADMIN` or if acting as an admin
            without an explicit `employer_id`, 409 if `email` is already
            registered.
    """
    if body.role not in _SELF_REGISTERABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only 'employer' and 'employee' accounts can be created here.",
        )
    target_employer_id = _resolve_target_employer_id(current_user, body.employer_id)
    if await employee_repository.get_by_email(body.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This email is already registered."
        )

    created = await employee_repository.create(
        Employee(
            employer_id=target_employer_id,
            email=body.email,
            hashed_password=AuthService.hash_password(body.password),
            full_name=body.full_name,
            role=body.role,
        )
    )
    return _to_response(created)


@router.get("", dependencies=[Depends(_require_manager)])
async def list_employees(
    employer_id: UUID = Depends(get_current_employer_id),
    employee_repository: EmployeeRepository = Depends(get_employee_repository),
) -> list[EmployeeResponse]:
    employees = await employee_repository.list_by_employer(employer_id)
    return [_to_response(employee) for employee in employees]


@router.get("/me/policies")
async def get_my_policies(
    current_user: TokenPayload = Depends(get_current_user),
    enrollment_repository: EnrollmentRepository = Depends(get_enrollment_repository),
    policy_repository: PolicyRepository = Depends(get_policy_repository),
) -> list[EnrolledPolicyResponse]:
    """The current user's own enrolled policies (files/plan.md Step
    9.4's `GET /api/employees/me/policies`)."""
    enrollments = await enrollment_repository.list_by_employee(current_user.user_id)
    response = []
    for enrollment in enrollments:
        policy = await policy_repository.get(enrollment.policy_id)
        if policy is None:
            continue
        response.append(
            EnrolledPolicyResponse(
                policy_id=policy.id,
                name=policy.name,
                policy_type=policy.policy_type,
                is_active=enrollment.is_active,
            )
        )
    return response


@router.get("/{employee_id}", dependencies=[Depends(_require_manager)])
async def get_employee(
    employee_id: UUID,
    current_user: TokenPayload = Depends(get_current_user),
    employee_repository: EmployeeRepository = Depends(get_employee_repository),
) -> EmployeeResponse:
    employee = await _get_managed_employee(employee_repository, employee_id, current_user)
    return _to_response(employee)


@router.patch("/{employee_id}", dependencies=[Depends(_require_manager)])
async def update_employee(
    employee_id: UUID,
    body: EmployeeUpdateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    employee_repository: EmployeeRepository = Depends(get_employee_repository),
) -> EmployeeResponse:
    employee = await _get_managed_employee(employee_repository, employee_id, current_user)
    updated = await employee_repository.update(
        employee.model_copy(update=body.model_dump(exclude_unset=True))
    )
    return _to_response(updated)


@router.delete(
    "/{employee_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_manager)],
)
async def delete_employee(
    employee_id: UUID,
    current_user: TokenPayload = Depends(get_current_user),
    employee_repository: EmployeeRepository = Depends(get_employee_repository),
) -> None:
    await _get_managed_employee(employee_repository, employee_id, current_user)
    await employee_repository.delete(employee_id)
