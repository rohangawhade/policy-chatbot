import pytest

from config import (
    AppConfig,
    AuthConfig,
    CacheConfig,
    CeleryConfig,
    CorsConfig,
    DatabaseConfig,
    LLMConfig,
    PineconeConfig,
    RedisConfig,
    app_config,
    auth_config,
    cache_config,
    celery_config,
    cors_config,
    database_config,
    llm_config,
    pinecone_config,
    redis_config,
)

# Every test below constructs its own instance with _env_file=None so it only
# sees explicitly-set env vars, not this machine's real (gitignored,
# possibly locally-edited) .env file — pydantic-settings supports this
# override on every BaseSettings subclass.


def test_module_level_singletons_are_the_expected_types() -> None:
    assert isinstance(app_config, AppConfig)
    assert isinstance(database_config, DatabaseConfig)
    assert isinstance(redis_config, RedisConfig)
    assert isinstance(cache_config, CacheConfig)
    assert isinstance(celery_config, CeleryConfig)
    assert isinstance(pinecone_config, PineconeConfig)
    assert isinstance(llm_config, LLMConfig)
    assert isinstance(auth_config, AuthConfig)
    assert isinstance(cors_config, CorsConfig)


def test_defaults_are_sane_and_non_secret() -> None:
    assert DatabaseConfig(_env_file=None).pool_size == 10  # type: ignore[call-arg]
    assert RedisConfig(_env_file=None).url.startswith("redis://")  # type: ignore[call-arg]
    assert CacheConfig(_env_file=None).ttl_seconds == 3600  # type: ignore[call-arg]
    assert AuthConfig(_env_file=None).jwt_algorithm == "HS256"  # type: ignore[call-arg]
    assert PineconeConfig(_env_file=None).api_key is None  # type: ignore[call-arg]


def test_llm_config_defaults_support_automatic_fallback() -> None:
    config = LLMConfig(_env_file=None)  # type: ignore[call-arg]
    assert config.fallback_enabled is True
    assert config.embedding_model != config.cheap_model


def test_env_vars_override_defaults_within_their_own_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("AUTH_ACCESS_TOKEN_EXPIRE_MINUTES", "30")

    config = AuthConfig(_env_file=None)  # type: ignore[call-arg]

    assert config.jwt_algorithm == "RS256"
    assert config.access_token_expire_minutes == 30


def test_env_prefixes_do_not_leak_across_config_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_JWT_ALGORITHM", "RS256")

    # A var under a different prefix must not affect an unrelated section.
    assert DatabaseConfig(_env_file=None).pool_size == 10  # type: ignore[call-arg]


def test_cors_allowed_origins_list_splits_and_trims() -> None:
    config = CorsConfig(  # type: ignore[call-arg]
        _env_file=None,
        allowed_origins="http://a.example, http://b.example ,http://c.example",
    )

    assert config.allowed_origins_list == [
        "http://a.example",
        "http://b.example",
        "http://c.example",
    ]


def test_cors_allowed_origins_list_handles_single_origin() -> None:
    assert CorsConfig(_env_file=None).allowed_origins_list == ["http://localhost:5173"]  # type: ignore[call-arg]
