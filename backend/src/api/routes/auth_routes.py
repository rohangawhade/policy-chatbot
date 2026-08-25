"""Auth routes (files/plan.md Step 9.1): register, login, refresh, and the
current user's profile. `AuthService` (Step 5.1) already implements every
piece of logic these need — this file is HTTP wiring only, no new service
logic.

**Response shape, a deliberate consistency choice**: `files/coding-standards.md`
section 7 asks for every response wrapped in a generic `APIResponse[T]`
envelope, but neither of the two route files that exist so far
(`health_routes.py`, `document_routes.py`) do that — both return their
Pydantic response model directly. Introducing the envelope here alone would
make the API surface inconsistent (one wrapped route file next to two
unwrapped ones) rather than fixing the gap, so this file matches the
established convention instead. Flagged in IMPLEMENTATION_STATUS.md as a
standing gap — adopting the envelope, if the team wants it, is a
cross-cutting change that should touch every route file at once, not be
decided ad hoc per file.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from api.dependencies import get_auth_service, get_employee_repository, get_employer_repository
from api.middleware.auth_middleware import get_current_user
from core.domain.employee import Employee, UserRole
from core.domain.errors import InvalidCredentialsError, InvalidTokenError
from core.ports.repository_ports import EmployeeRepository, EmployerRepository
from core.services.auth_service import AuthService, TokenPayload

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Only these two roles are self-registerable. ADMIN is a superuser scoped
# to no employer (core/domain/employee.py) — created out-of-band, never
# through open registration.
_SELF_REGISTERABLE_ROLES = (UserRole.EMPLOYER, UserRole.EMPLOYEE)


class RegisterRequest(BaseModel):
    employer_id: UUID
    email: str
    password: str
    full_name: str
    role: UserRole


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class EmployeeProfileResponse(BaseModel):
    id: UUID
    employer_id: UUID | None
    email: str
    full_name: str
    role: UserRole
    is_active: bool


def _to_profile(employee: Employee) -> EmployeeProfileResponse:
    return EmployeeProfileResponse(
        id=employee.id,
        employer_id=employee.employer_id,
        email=employee.email,
        full_name=employee.full_name,
        role=employee.role,
        is_active=employee.is_active,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    employee_repository: EmployeeRepository = Depends(get_employee_repository),
    employer_repository: EmployerRepository = Depends(get_employer_repository),
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Create a new employer-contact or employee account under an existing
    employer, then immediately issue a token pair — same as `/login` would,
    sparing the caller a second round trip right after registering.

    Raises:
        HTTPException: 422 if `role` is `ADMIN` (not self-registerable),
            404 if `employer_id` doesn't reference a real employer, 409 if
            `email` is already registered.
    """
    if body.role not in _SELF_REGISTERABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only 'employer' and 'employee' accounts can self-register.",
        )
    if await employer_repository.get(body.employer_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employer not found.")
    if await employee_repository.get_by_email(body.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This email is already registered."
        )

    employee = Employee(
        employer_id=body.employer_id,
        email=body.email,
        hashed_password=AuthService.hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
    )
    created = await employee_repository.create(employee)
    tokens = auth_service.issue_token_pair(created)
    return TokenResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """OAuth2 password flow: `username` is the account's email.

    Raises:
        HTTPException: 401 if the email/password combination doesn't match
            an active account.
    """
    try:
        tokens = await auth_service.authenticate(form_data.username, form_data.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return TokenResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/refresh")
async def refresh(
    body: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> AccessTokenResponse:
    """Exchange a still-valid refresh token for a fresh access token.

    Raises:
        HTTPException: 401 if the refresh token is malformed, expired, or
            not actually a refresh token.
    """
    try:
        access_token = auth_service.refresh_access_token(body.refresh_token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return AccessTokenResponse(access_token=access_token)


@router.get("/me")
async def me(
    current_user: TokenPayload = Depends(get_current_user),
    employee_repository: EmployeeRepository = Depends(get_employee_repository),
) -> EmployeeProfileResponse:
    """The authenticated account's own profile.

    `hashed_password` is deliberately excluded from the response — it's
    domain data (core/domain/employee.py Step 2.1), but never something an
    API response should echo back.

    Raises:
        HTTPException: 404 if the token's subject no longer exists (e.g.
            the account was deleted after the token was issued).
    """
    employee = await employee_repository.get(current_user.user_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    return _to_profile(employee)
