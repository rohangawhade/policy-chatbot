from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import cors_config
from main import create_app


def test_create_app_returns_configured_fastapi_instance() -> None:
    app = create_app()

    assert isinstance(app, FastAPI)
    assert app.title == "PolicyPal"
    assert app.version == "0.1.0"


def test_cors_preflight_allows_the_configured_frontend_origin() -> None:
    client = TestClient(create_app())
    origin = cors_config.allowed_origins_list[0]

    response = client.options(
        "/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )

    assert response.headers["access-control-allow-origin"] == origin


def test_cors_allows_the_configured_origin_on_a_real_request() -> None:
    # A real (non-preflight) cross-origin request needs the header too --
    # this is what actually failed before CORSMiddleware was wired in:
    # `curl`/TestClient calls with no Origin header never exercised CORS
    # at all, so the gap went uncaught until a real browser hit it.
    client = TestClient(create_app())
    origin = cors_config.allowed_origins_list[0]

    response = client.get("/health", headers={"Origin": origin})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_cors_rejects_an_unconfigured_origin() -> None:
    client = TestClient(create_app())

    response = client.get("/health", headers={"Origin": "http://evil.example"})

    assert "access-control-allow-origin" not in response.headers
