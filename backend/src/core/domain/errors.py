"""Custom exception hierarchy (files/coding-standards.md section 6).

`DocumentProcessingError`/`UnsupportedFormatError` (Step 3.6's
`ProcessorFactory`) and `AuthenticationError`'s two subclasses (Step
5.1's `AuthService`) predate this file's full hierarchy. Step 14.2 added
the rest of section 6's named classes (`DomainError`, `NotFoundError`,
`AuthorizationError`, `TenantAccessError`, `RateLimitError`,
`ModelUnavailableError`) verbatim, plus `api/error_handlers.py`, the
"API layer converts domain exceptions to appropriate HTTP status codes"
piece section 6 asks for — a route/service can raise any of these
without importing `fastapi` at all.
"""


class PolicyPalError(Exception):
    """Base exception for all app errors."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class DomainError(PolicyPalError):
    """Business rule violation."""


class NotFoundError(PolicyPalError):
    """Requested entity does not exist."""


class AuthorizationError(PolicyPalError):
    """User lacks permission for this action."""


class TenantAccessError(AuthorizationError):
    """User tried to access another employer's data."""


class RateLimitError(PolicyPalError):
    """User exceeded allowed request rate."""


class ModelUnavailableError(PolicyPalError):
    """Requested LLM model tier is not configured or unreachable."""


class DocumentProcessingError(PolicyPalError):
    """Document ingestion or parsing failed."""


class UnsupportedFormatError(DocumentProcessingError):
    """No processor is registered for the requested file extension."""

    def __init__(self, extension: str) -> None:
        super().__init__(
            f"No document processor registered for extension: {extension!r}",
            code="unsupported_format",
        )
        self.extension = extension


class AuthenticationError(PolicyPalError):
    """The caller could not be identified — bad credentials or a bad
    token. Distinct from `AuthorizationError` (section 6's hierarchy),
    which is about a known caller lacking permission, not identity."""


class InvalidCredentialsError(AuthenticationError):
    """Login email/password didn't match any active account.

    Deliberately the same error for "no such email" and "wrong
    password" — never let a caller distinguish the two.
    """

    def __init__(self) -> None:
        super().__init__("Invalid email or password.", code="invalid_credentials")


class InvalidTokenError(AuthenticationError):
    """A JWT was malformed, expired, unsigned by this service, or the
    wrong type (e.g. a refresh token presented where an access token
    was expected)."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid token: {reason}", code="invalid_token")
        self.reason = reason
