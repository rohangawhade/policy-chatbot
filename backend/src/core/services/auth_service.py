"""OAuth2 password flow: authenticates employees and issues/validates
JWT access + refresh tokens (files/plan.md Step 5.1,
files/coding-standards.md section 8). Depends only on ports/domain — the
HTTP token endpoint is Phase 9's job; Step 5.2's auth middleware will
call `decode_token()` to authenticate incoming requests.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from core.domain.employee import Employee, UserRole
from core.domain.errors import InvalidCredentialsError, InvalidTokenError
from core.ports.repository_ports import EmployeeRepository

_ACCESS_TOKEN_TYPE = "access"
_REFRESH_TOKEN_TYPE = "refresh"

# bcrypt, 12 rounds minimum per coding-standards.md section 8. Module-level
# singleton — passlib's own recommended usage, avoids rebuilding the
# context (cheap) on every hash/verify call (the expensive part).
_password_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12)


@dataclass(frozen=True, kw_only=True)
class TokenPair:
    access_token: str
    refresh_token: str


@dataclass(frozen=True, kw_only=True)
class TokenPayload:
    """Decoded, validated claims from an access or refresh token."""

    user_id: UUID
    employer_id: UUID | None
    role: UserRole
    token_type: str


class AuthService:
    """Authenticates employees by email/password and issues/validates JWTs.

    Attributes:
        employee_repository: Looks up the account by email at login.
        secret_key: HMAC signing key for every token this service issues
            or verifies.
        algorithm: JWT signing algorithm (e.g. "HS256").
        access_token_expire_minutes: Access token lifetime.
        refresh_token_expire_days: Refresh token lifetime.
    """

    def __init__(
        self,
        employee_repository: EmployeeRepository,
        secret_key: str,
        algorithm: str,
        access_token_expire_minutes: int,
        refresh_token_expire_days: int,
    ) -> None:
        self._employee_repository = employee_repository
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._access_token_expire_minutes = access_token_expire_minutes
        self._refresh_token_expire_days = refresh_token_expire_days

    @staticmethod
    def hash_password(password: str) -> str:
        hashed: str = _password_context.hash(password)
        return hashed

    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        valid: bool = _password_context.verify(password, hashed_password)
        return valid

    async def authenticate(self, email: str, password: str) -> TokenPair:
        """Verify credentials and issue a fresh access + refresh token pair.

        Raises:
            InvalidCredentialsError: No active account matches `email`,
                or `password` is wrong.
        """
        employee = await self._employee_repository.get_by_email(email)
        if employee is None or not employee.is_active:
            raise InvalidCredentialsError()
        if not self.verify_password(password, employee.hashed_password):
            raise InvalidCredentialsError()
        return self.issue_token_pair(employee)

    def refresh_access_token(self, refresh_token: str) -> str:
        """Verify a refresh token and issue a new access token from it.

        Stateless by design — does not re-check the account is still
        active. A revocation/deny-list mechanism is out of this step's
        scope; every issued refresh token remains valid until it expires.

        Raises:
            InvalidTokenError: The token is malformed, expired, or not a
                refresh token.
        """
        payload = self.decode_token(refresh_token)
        if payload.token_type != _REFRESH_TOKEN_TYPE:
            raise InvalidTokenError("expected a refresh token")
        return self._create_token(
            payload.user_id,
            payload.employer_id,
            payload.role,
            token_type=_ACCESS_TOKEN_TYPE,
            expires_delta=timedelta(minutes=self._access_token_expire_minutes),
        )

    def decode_token(self, token: str) -> TokenPayload:
        """Decode and validate a token's signature, expiry, and claims.

        Raises:
            InvalidTokenError: The token is malformed, unsigned by this
                service, expired, or missing a required claim.
        """
        try:
            claims = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
        except JWTError as exc:
            raise InvalidTokenError(str(exc)) from exc

        try:
            employer_id_claim = claims.get("employer_id")
            return TokenPayload(
                user_id=UUID(claims["sub"]),
                employer_id=UUID(employer_id_claim) if employer_id_claim else None,
                role=UserRole(claims["role"]),
                token_type=claims["token_type"],
            )
        except (KeyError, ValueError) as exc:
            raise InvalidTokenError("missing or malformed claims") from exc

    def issue_token_pair(self, employee: Employee) -> TokenPair:
        """Mint a fresh access + refresh token pair for an already-known,
        already-authenticated (or just-created) account.

        Public because Step 9.1's registration route needs to issue tokens
        for a brand-new account without re-verifying a password it was
        never given a reason to doubt — `authenticate()` uses this
        internally too, for the login path.
        """
        access_token = self._create_token(
            employee.id,
            employee.employer_id,
            employee.role,
            token_type=_ACCESS_TOKEN_TYPE,
            expires_delta=timedelta(minutes=self._access_token_expire_minutes),
        )
        refresh_token = self._create_token(
            employee.id,
            employee.employer_id,
            employee.role,
            token_type=_REFRESH_TOKEN_TYPE,
            expires_delta=timedelta(days=self._refresh_token_expire_days),
        )
        return TokenPair(access_token=access_token, refresh_token=refresh_token)

    def _create_token(
        self,
        user_id: UUID,
        employer_id: UUID | None,
        role: UserRole,
        *,
        token_type: str,
        expires_delta: timedelta,
    ) -> str:
        now = datetime.now(UTC)
        claims = {
            "sub": str(user_id),
            "employer_id": str(employer_id) if employer_id is not None else None,
            "role": role.value,
            "token_type": token_type,
            "iat": now,
            "exp": now + expires_delta,
        }
        encoded: str = jwt.encode(claims, self._secret_key, algorithm=self._algorithm)
        return encoded
