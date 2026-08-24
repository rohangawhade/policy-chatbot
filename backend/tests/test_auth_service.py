from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from jose import jwt

from core.domain.employee import Employee, UserRole
from core.domain.errors import InvalidCredentialsError, InvalidTokenError
from core.ports.repository_ports import EmployeeRepository
from core.services.auth_service import AuthService, TokenPayload

_SECRET_KEY = "test-secret-key"
_ALGORITHM = "HS256"
_ACCESS_MINUTES = 15
_REFRESH_DAYS = 7


class FakeEmployeeRepository(EmployeeRepository):
    def __init__(self, employees: list[Employee]) -> None:
        self._by_email = {employee.email: employee for employee in employees}

    async def get(self, entity_id: UUID) -> Employee | None:
        raise NotImplementedError

    async def create(self, entity: Employee) -> Employee:
        raise NotImplementedError

    async def update(self, entity: Employee) -> Employee:
        raise NotImplementedError

    async def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError

    async def get_by_email(self, email: str) -> Employee | None:
        return self._by_email.get(email)

    async def list_by_employer(self, employer_id: UUID) -> list[Employee]:
        raise NotImplementedError


def _employee(**overrides: Any) -> Employee:
    defaults: dict[str, Any] = {
        "employer_id": uuid4(),
        "email": "jane@acme.com",
        "hashed_password": AuthService.hash_password("correct-password"),
        "full_name": "Jane Doe",
        "role": UserRole.EMPLOYEE,
        "is_active": True,
    }
    defaults.update(overrides)
    return Employee(**defaults)


def _service(*employees: Employee) -> AuthService:
    return AuthService(
        FakeEmployeeRepository(list(employees)),
        secret_key=_SECRET_KEY,
        algorithm=_ALGORITHM,
        access_token_expire_minutes=_ACCESS_MINUTES,
        refresh_token_expire_days=_REFRESH_DAYS,
    )


def _build_token(
    *,
    secret_key: str = _SECRET_KEY,
    user_id: UUID | None = None,
    employer_id: UUID | None = None,
    role: UserRole = UserRole.EMPLOYEE,
    token_type: str = "access",
    expires_delta: timedelta = timedelta(minutes=5),
) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id or uuid4()),
        "employer_id": str(employer_id) if employer_id is not None else None,
        "role": role.value,
        "token_type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    token: str = jwt.encode(claims, secret_key, algorithm=_ALGORITHM)
    return token


def test_hash_password_produces_a_verifiable_but_different_string() -> None:
    hashed = AuthService.hash_password("s3cret!")

    assert hashed != "s3cret!"
    assert AuthService.verify_password("s3cret!", hashed) is True


def test_verify_password_rejects_a_wrong_password() -> None:
    hashed = AuthService.hash_password("s3cret!")

    assert AuthService.verify_password("wrong", hashed) is False


async def test_authenticate_issues_a_token_pair_for_valid_credentials() -> None:
    employee = _employee()
    service = _service(employee)

    tokens = await service.authenticate(employee.email, "correct-password")

    access_payload = service.decode_token(tokens.access_token)
    refresh_payload = service.decode_token(tokens.refresh_token)
    assert access_payload == TokenPayload(
        user_id=employee.id,
        employer_id=employee.employer_id,
        role=UserRole.EMPLOYEE,
        token_type="access",
    )
    assert refresh_payload.token_type == "refresh"
    assert refresh_payload.user_id == employee.id


async def test_authenticate_rejects_an_unknown_email() -> None:
    service = _service()

    with pytest.raises(InvalidCredentialsError):
        await service.authenticate("nobody@acme.com", "whatever")


async def test_authenticate_rejects_an_inactive_account() -> None:
    employee = _employee(is_active=False)
    service = _service(employee)

    with pytest.raises(InvalidCredentialsError):
        await service.authenticate(employee.email, "correct-password")


async def test_authenticate_rejects_a_wrong_password() -> None:
    employee = _employee()
    service = _service(employee)

    with pytest.raises(InvalidCredentialsError):
        await service.authenticate(employee.email, "wrong-password")


async def test_authenticate_handles_an_admin_with_no_employer_id() -> None:
    admin = _employee(employer_id=None, role=UserRole.ADMIN)
    service = _service(admin)

    tokens = await service.authenticate(admin.email, "correct-password")

    payload = service.decode_token(tokens.access_token)
    assert payload.employer_id is None
    assert payload.role == UserRole.ADMIN


def test_decode_token_rejects_a_token_signed_with_a_different_key() -> None:
    service = _service()
    token = _build_token(secret_key="a-different-secret")

    with pytest.raises(InvalidTokenError):
        service.decode_token(token)


def test_decode_token_rejects_an_expired_token() -> None:
    service = _service()
    token = _build_token(expires_delta=timedelta(minutes=-1))

    with pytest.raises(InvalidTokenError):
        service.decode_token(token)


def test_decode_token_rejects_a_token_missing_required_claims() -> None:
    service = _service()
    now = datetime.now(UTC)
    incomplete = jwt.encode(
        {"sub": str(uuid4()), "iat": now, "exp": now + timedelta(minutes=5)},
        _SECRET_KEY,
        algorithm=_ALGORITHM,
    )

    with pytest.raises(InvalidTokenError):
        service.decode_token(incomplete)


def test_decode_token_rejects_garbage_input() -> None:
    service = _service()

    with pytest.raises(InvalidTokenError):
        service.decode_token("not-a-real-token")


def test_refresh_access_token_issues_a_new_access_token() -> None:
    service = _service()
    user_id, employer_id = uuid4(), uuid4()
    refresh_token = _build_token(
        user_id=user_id,
        employer_id=employer_id,
        role=UserRole.EMPLOYER,
        token_type="refresh",
        expires_delta=timedelta(days=_REFRESH_DAYS),
    )

    new_access_token = service.refresh_access_token(refresh_token)

    payload = service.decode_token(new_access_token)
    assert payload == TokenPayload(
        user_id=user_id, employer_id=employer_id, role=UserRole.EMPLOYER, token_type="access"
    )


def test_refresh_access_token_rejects_an_access_token() -> None:
    service = _service()
    access_token = _build_token(token_type="access")

    with pytest.raises(InvalidTokenError):
        service.refresh_access_token(access_token)
