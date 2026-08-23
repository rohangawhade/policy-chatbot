"""Typed, environment-driven application configuration.

Every setting is validated Pydantic Settings, sourced from environment
variables (see .env.example) or, for local host-based development, the
repo-root .env file. No secrets are ever hardcoded here — every default
below is either a non-secret (a model name, a port) or an obviously-fake
placeholder ("changeme") that must be overridden in real environments.

Each config class is independently instantiable (its own env_prefix), per
files/coding-standards.md section 10. Real environment variables always take
precedence over the .env file, so Docker Compose's `env_file`/`environment`
overrides (see docker-compose.yml) work exactly as before.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class _Config(BaseSettings):
    """Base for all config sections: reads the repo-root .env if present,
    ignores unrelated keys in it (each section only cares about its own
    prefix), and lets real env vars win over the file."""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")


class AppConfig(_Config):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=_ENV_FILE, extra="ignore")

    env: str = "development"
    debug: bool = True
    secret_key: str = "changeme"


class DatabaseConfig(_Config):
    model_config = SettingsConfigDict(env_prefix="DATABASE_", env_file=_ENV_FILE, extra="ignore")

    url: str = "postgresql+asyncpg://policypal:policypal@localhost:5432/policypal"
    pool_size: int = 10


class RedisConfig(_Config):
    model_config = SettingsConfigDict(env_prefix="REDIS_", env_file=_ENV_FILE, extra="ignore")

    url: str = "redis://localhost:6379/0"


class CacheConfig(_Config):
    model_config = SettingsConfigDict(env_prefix="CACHE_", env_file=_ENV_FILE, extra="ignore")

    ttl_seconds: int = 3600


class CeleryConfig(_Config):
    model_config = SettingsConfigDict(env_prefix="CELERY_", env_file=_ENV_FILE, extra="ignore")

    broker_url: str = "redis://localhost:6379/1"
    result_backend: str = "redis://localhost:6379/2"


class PineconeConfig(_Config):
    model_config = SettingsConfigDict(env_prefix="PINECONE_", env_file=_ENV_FILE, extra="ignore")

    api_key: str | None = None
    environment: str | None = None
    index_name: str = "policypal"


class LLMConfig(_Config):
    """Model tiers are config-driven. If powerful_model is empty or its
    provider key is missing, every query falls back to cheap_model —
    no code changes needed (see plan.md's Multi-Model Routing Strategy).
    embedding_model is intentionally separate: embeddings use a different,
    cheaper model than generation.
    """

    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=_ENV_FILE, extra="ignore")

    cheap_model: str = "claude-haiku-4-5-20251001"
    powerful_model: str | None = "claude-sonnet-4-6"
    embedding_model: str = "text-embedding-3-small"
    complexity_threshold: float = 0.4
    temperature: float = 0.1
    max_tokens: int = 2048
    streaming_enabled: bool = True
    fallback_enabled: bool = True


class AuthConfig(_Config):
    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=_ENV_FILE, extra="ignore")

    jwt_secret_key: str = "changeme"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7


class CorsConfig(_Config):
    model_config = SettingsConfigDict(env_prefix="CORS_", env_file=_ENV_FILE, extra="ignore")

    allowed_origins: str = "http://localhost:5173"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


app_config = AppConfig()
database_config = DatabaseConfig()
redis_config = RedisConfig()
cache_config = CacheConfig()
celery_config = CeleryConfig()
pinecone_config = PineconeConfig()
llm_config = LLMConfig()
auth_config = AuthConfig()
cors_config = CorsConfig()
