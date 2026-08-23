from fastapi import FastAPI

from main import create_app


def test_create_app_returns_configured_fastapi_instance() -> None:
    app = create_app()

    assert isinstance(app, FastAPI)
    assert app.title == "PolicyPal"
    assert app.version == "0.1.0"
