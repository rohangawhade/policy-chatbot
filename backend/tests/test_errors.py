from core.domain.errors import (
    AuthenticationError,
    DocumentProcessingError,
    InvalidCredentialsError,
    InvalidTokenError,
    PolicyPalError,
    UnsupportedFormatError,
)


def test_policypal_error_carries_message_and_code() -> None:
    error = PolicyPalError("something went wrong", code="generic_error")

    assert str(error) == "something went wrong"
    assert error.message == "something went wrong"
    assert error.code == "generic_error"


def test_document_processing_error_is_a_policypal_error() -> None:
    error = DocumentProcessingError("parsing failed", code="parsing_failed")

    assert isinstance(error, PolicyPalError)


def test_unsupported_format_error_is_a_document_processing_error() -> None:
    error = UnsupportedFormatError("csv")

    assert isinstance(error, DocumentProcessingError)
    assert isinstance(error, PolicyPalError)


def test_unsupported_format_error_carries_the_extension_and_a_readable_message() -> None:
    error = UnsupportedFormatError("csv")

    assert error.extension == "csv"
    assert error.code == "unsupported_format"
    assert "csv" in str(error)


def test_invalid_credentials_error_is_an_authentication_error() -> None:
    error = InvalidCredentialsError()

    assert isinstance(error, AuthenticationError)
    assert isinstance(error, PolicyPalError)
    assert error.code == "invalid_credentials"
    assert str(error) == "Invalid email or password."


def test_invalid_token_error_is_an_authentication_error() -> None:
    error = InvalidTokenError("expired")

    assert isinstance(error, AuthenticationError)
    assert isinstance(error, PolicyPalError)
    assert error.code == "invalid_token"
    assert error.reason == "expired"
    assert "expired" in str(error)
