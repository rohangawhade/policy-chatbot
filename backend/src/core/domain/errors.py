"""Custom exception hierarchy (files/coding-standards.md section 6).

Only the exceptions an actual caller needs today are defined here —
`DocumentProcessingError`/`UnsupportedFormatError` for Step 3.6's
`ProcessorFactory` (section 1's Open/Closed example names
`UnsupportedFormatError` directly). Extend with
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
