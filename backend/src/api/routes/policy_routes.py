"""Policy CRUD and enrollment (files/plan.md Step 9.4's "Policy
assignment: enroll/unenroll employees from policies").

Response shape matches the established convention from Step 9.1 (see
`auth_routes.py`'s module docstring) — this file returns its Pydantic
model(s) directly, not wrapped in `files/coding-standards.md` section
7's `APIResponse[T]` envelope.

**Deliberate scope decision**: unlike `document_routes.py`'s upload
route, policy management here does *not* accept an explicit
`employer_id` for admin callers — `get_current_employer_id` (which
403s for an `ADMIN`, who has none) scopes every route in this file.
Nothing in `files/plan.md`'s Step 9.4 text calls out admin access to
policy management specifically (only employer CRUD is named
"admin only"), so this stays simple rather than speculatively adding
the same admin carve-out everywhere.

**Added for Step 10.8**: `GET /{policy_id}/enrollments`.
`EnrollmentRepository.list_by_policy` (Step 2.2/3.5) already existed and
was already implemented (`PostgresEnrollmentRepository`), but nothing
routed to it — `files/plan.md`'s Step 10.8 employer-portal bullet
("policy overview: ... which employees are enrolled") needs exactly
this and there was no way to get it. Gated behind `_require_manager`
like every other route here that returns employee PII (matching
`employee_routes.py`'s stricter-than-document-list default for the
same reason).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.dependencies import (
    get_employee_repository,
    get_enrollment_repository,
    get_policy_repository,
)
from api.middleware.auth_middleware import require_role
from api.middleware.tenant_context import get_current_employer_id
from core.domain.employee import UserRole
from core.domain.policy import Enrollment, Policy, PolicyType
from core.ports.repository_ports import EmployeeRepository, EnrollmentRepository, PolicyRepository

router = APIRouter(prefix="/api/policies", tags=["policies"])

_require_manager = require_role(UserRole.EMPLOYER, UserRole.ADMIN)


class PolicyResponse(BaseModel):
    id: UUID
    employer_id: UUID
    policy_type: PolicyType
    name: str
    description: str | None


class PolicyCreateRequest(BaseModel):
    policy_type: PolicyType
    name: str
    description: str | None = None


class PolicyUpdateRequest(BaseModel):
    policy_type: PolicyType | None = None
    name: str | None = None
    description: str | None = None


class EnrollmentRequest(BaseModel):
    employee_id: UUID


class EnrollmentResponse(BaseModel):
    employee_id: UUID
    policy_id: UUID
    is_active: bool


class EnrolledEmployeeResponse(BaseModel):
    employee_id: UUID
    full_name: str
    email: str
    is_active: bool


def _to_response(policy: Policy) -> PolicyResponse:
    return PolicyResponse(
        id=policy.id,
        employer_id=policy.employer_id,
        policy_type=policy.policy_type,
        name=policy.name,
        description=policy.description,
    )


async def _get_owned_policy(
    policy_repository: PolicyRepository, policy_id: UUID, employer_id: UUID
) -> Policy:
    policy = await policy_repository.get(policy_id)
    if policy is None or policy.employer_id != employer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found.")
    return policy


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_require_manager)])
async def create_policy(
    body: PolicyCreateRequest,
    employer_id: UUID = Depends(get_current_employer_id),
    policy_repository: PolicyRepository = Depends(get_policy_repository),
) -> PolicyResponse:
    created = await policy_repository.create(
        Policy(
            employer_id=employer_id,
            policy_type=body.policy_type,
            name=body.name,
            description=body.description,
        )
    )
    return _to_response(created)


@router.get("")
async def list_policies(
    employer_id: UUID = Depends(get_current_employer_id),
    policy_repository: PolicyRepository = Depends(get_policy_repository),
) -> list[PolicyResponse]:
    policies = await policy_repository.list_by_employer(employer_id)
    return [_to_response(policy) for policy in policies]


@router.get("/{policy_id}")
async def get_policy(
    policy_id: UUID,
    employer_id: UUID = Depends(get_current_employer_id),
    policy_repository: PolicyRepository = Depends(get_policy_repository),
) -> PolicyResponse:
    policy = await _get_owned_policy(policy_repository, policy_id, employer_id)
    return _to_response(policy)


@router.get("/{policy_id}/enrollments", dependencies=[Depends(_require_manager)])
async def list_policy_enrollments(
    policy_id: UUID,
    employer_id: UUID = Depends(get_current_employer_id),
    policy_repository: PolicyRepository = Depends(get_policy_repository),
    employee_repository: EmployeeRepository = Depends(get_employee_repository),
    enrollment_repository: EnrollmentRepository = Depends(get_enrollment_repository),
) -> list[EnrolledEmployeeResponse]:
    """Which employees are enrolled in this policy (files/plan.md Step
    10.8's employer-portal policy overview)."""
    await _get_owned_policy(policy_repository, policy_id, employer_id)
    enrollments = await enrollment_repository.list_by_policy(policy_id)

    response = []
    for enrollment in enrollments:
        employee = await employee_repository.get(enrollment.employee_id)
        if employee is None:
            continue
        response.append(
            EnrolledEmployeeResponse(
                employee_id=employee.id,
                full_name=employee.full_name,
                email=employee.email,
                is_active=enrollment.is_active,
            )
        )
    return response


@router.patch("/{policy_id}", dependencies=[Depends(_require_manager)])
async def update_policy(
    policy_id: UUID,
    body: PolicyUpdateRequest,
    employer_id: UUID = Depends(get_current_employer_id),
    policy_repository: PolicyRepository = Depends(get_policy_repository),
) -> PolicyResponse:
    policy = await _get_owned_policy(policy_repository, policy_id, employer_id)
    updated = await policy_repository.update(
        policy.model_copy(update=body.model_dump(exclude_unset=True))
    )
    return _to_response(updated)


@router.delete(
    "/{policy_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_require_manager)]
)
async def delete_policy(
    policy_id: UUID,
    employer_id: UUID = Depends(get_current_employer_id),
    policy_repository: PolicyRepository = Depends(get_policy_repository),
) -> None:
    await _get_owned_policy(policy_repository, policy_id, employer_id)
    await policy_repository.delete(policy_id)


@router.post(
    "/{policy_id}/enroll",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_manager)],
)
async def enroll_employee(
    policy_id: UUID,
    body: EnrollmentRequest,
    employer_id: UUID = Depends(get_current_employer_id),
    policy_repository: PolicyRepository = Depends(get_policy_repository),
    employee_repository: EmployeeRepository = Depends(get_employee_repository),
    enrollment_repository: EnrollmentRepository = Depends(get_enrollment_repository),
) -> EnrollmentResponse:
    """Enroll an employee in a policy.

    Reactivates an existing (possibly previously-unenrolled) enrollment
    rather than creating a second row when one already exists — the
    schema's `(employee_id, policy_id)` unique constraint
    (`files/plan.md` Step 1.3) only ever allows one.

    Raises:
        HTTPException: 404 if the policy or employee doesn't belong to
            the current employer.
    """
    await _get_owned_policy(policy_repository, policy_id, employer_id)
    employee = await employee_repository.get(body.employee_id)
    if employee is None or employee.employer_id != employer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found.")

    existing = await _find_enrollment(enrollment_repository, body.employee_id, policy_id)
    if existing is not None:
        enrollment = await enrollment_repository.update(
            existing.model_copy(update={"is_active": True})
        )
    else:
        enrollment = await enrollment_repository.create(
            Enrollment(employee_id=body.employee_id, policy_id=policy_id)
        )
    return EnrollmentResponse(
        employee_id=enrollment.employee_id,
        policy_id=enrollment.policy_id,
        is_active=enrollment.is_active,
    )


@router.delete(
    "/{policy_id}/enroll/{employee_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_manager)],
)
async def unenroll_employee(
    policy_id: UUID,
    employee_id: UUID,
    employer_id: UUID = Depends(get_current_employer_id),
    policy_repository: PolicyRepository = Depends(get_policy_repository),
    enrollment_repository: EnrollmentRepository = Depends(get_enrollment_repository),
) -> None:
    """Unenroll an employee from a policy — a soft-delete (`is_active =
    False`), not a row removal, preserving enrollment history."""
    await _get_owned_policy(policy_repository, policy_id, employer_id)
    existing = await _find_enrollment(enrollment_repository, employee_id, policy_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found.")
    await enrollment_repository.update(existing.model_copy(update={"is_active": False}))


async def _find_enrollment(
    enrollment_repository: EnrollmentRepository, employee_id: UUID, policy_id: UUID
) -> Enrollment | None:
    """No `get_by_employee_and_policy` port method exists — `EnrollmentRepository`
    only offers `list_by_employee`/`list_by_policy` (Step 2.2) — so this
    filters the (small, per-employee) list in-process rather than adding
    a new port method for a single caller."""
    enrollments = await enrollment_repository.list_by_employee(employee_id)
    return next((e for e in enrollments if e.policy_id == policy_id), None)
