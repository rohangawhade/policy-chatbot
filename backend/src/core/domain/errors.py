"""Custom exception hierarchy (files/coding-standards.md section 6).

Only the exceptions an actual caller needs today are defined here —
`DocumentProcessingError`/`UnsupportedFormatError` for Step 3.6's
`ProcessorFactory` (section 1's Open/Closed example names
`UnsupportedFormatError` directly), `AuthenticationError` and its two
subclasses for Step 5.1's `AuthService`. Extend with
`AuthorizationError`/`TenantAccessError`/`RateLimitError`/
`ModelUnavailableError` etc. from the same section whenever a later
phase actually raises one — no point defining exception classes nothing
throws yet.
"""


class PolicyPalError(Exception):
    """Base exception for all app errors."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


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
