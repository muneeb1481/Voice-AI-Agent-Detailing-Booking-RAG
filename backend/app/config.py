from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+pysqlite:///./dev.db"

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720

    admin_email: str = "admin@example.com"
    admin_password: str = "changeme"

    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    kimi_api_key: str = ""
    kimi_model: str = "kimi-k3"
    kimi_reasoning_effort: str = "low"

    groq_api_keys: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    vapi_secret: str = ""

    cors_origins: str = "http://localhost:5173"

    brand_name: str = "ShinePro Detailing"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def groq_key_list(self) -> list[str]:
        return [k.strip() for k in self.groq_api_keys.split(",") if k.strip()]

    @property
    def uses_postgres(self) -> bool:
        return self.database_url.startswith("postgres")


@lru_cache
def get_settings() -> Settings:
    return Settings()
