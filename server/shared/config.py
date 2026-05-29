from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str
    auth_database_url: str
    test_database_url: str

    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dim: int = 512

    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: str | None = None

    elasticsearch_url: str | None = None
    elasticsearch_index: str = "roadbuilders_text"

    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "roadbuilders"

    openrouter_api_key: str | None = None
    anthropic_api_key: str | None = None
    jwt_secret: str | None = None


settings = Settings()  # type: ignore[call-arg]
