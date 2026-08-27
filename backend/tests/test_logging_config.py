import pytest
import structlog

from config import app_config
from logging_config import configure_logging


@pytest.fixture(autouse=True)
def _reset_structlog_after_test() -> None:
    """Every test in this file mutates global `structlog` configuration
    (that's the whole point of `configure_logging()`) -- reset it back to
    library defaults afterward so no other test in the suite observes a
    renderer/level left over from here."""
    yield
    structlog.reset_defaults()


def _log_and_capture(
    capsys: pytest.CaptureFixture[str], level: str, event: str, **kwargs: object
) -> str:
    logger = structlog.get_logger("test_logging_config")
    getattr(logger, level)(event, **kwargs)
    return capsys.readouterr().out


def test_production_env_renders_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(app_config, "env", "production")
    monkeypatch.setattr(app_config, "debug", False)

    configure_logging()
    output = _log_and_capture(capsys, "info", "something_happened", foo="bar")

    assert output.startswith("{")
    assert '"event": "something_happened"' in output
    assert '"foo": "bar"' in output
    assert '"level": "info"' in output


def test_staging_env_renders_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(app_config, "env", "staging")
    monkeypatch.setattr(app_config, "debug", False)

    configure_logging()
    output = _log_and_capture(capsys, "info", "something_happened", foo="bar")

    assert output.startswith("{")
    assert '"event": "something_happened"' in output
    assert '"foo": "bar"' in output


def test_non_production_env_renders_pretty_console_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(app_config, "env", "development")
    monkeypatch.setattr(app_config, "debug", False)

    configure_logging()
    output = _log_and_capture(capsys, "info", "something_happened", foo="bar")

    assert not output.startswith("{")
    assert "something_happened" in output
    assert "foo" in output


def test_debug_true_emits_debug_level_logs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(app_config, "env", "development")
    monkeypatch.setattr(app_config, "debug", True)

    configure_logging()
    output = _log_and_capture(capsys, "debug", "internal_state", value=1)

    assert "internal_state" in output


def test_debug_false_suppresses_debug_level_logs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(app_config, "env", "development")
    monkeypatch.setattr(app_config, "debug", False)

    configure_logging()
    output = _log_and_capture(capsys, "debug", "internal_state", value=1)

    assert output == ""


def test_contextvars_are_merged_into_every_log_entry(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(app_config, "env", "production")
    monkeypatch.setattr(app_config, "debug", False)
    configure_logging()

    structlog.contextvars.bind_contextvars(correlation_id="abc-123")
    try:
        output = _log_and_capture(capsys, "info", "something_happened")
    finally:
        structlog.contextvars.clear_contextvars()

    assert '"correlation_id": "abc-123"' in output


def test_exception_info_is_rendered_for_logger_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(app_config, "env", "production")
    monkeypatch.setattr(app_config, "debug", False)
    configure_logging()

    logger = structlog.get_logger("test_logging_config")
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("operation_failed")
    output = capsys.readouterr().out

    assert '"level": "error"' in output
    assert "ValueError" in output
    assert "boom" in output
