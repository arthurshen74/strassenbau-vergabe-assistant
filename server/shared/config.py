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

    postgres_user: str
    postgres_password: str
    postgres_db: str = "roadbuilders"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    minio_root_user: str
    minio_root_password: str
    s3_host: str = "localhost"
    s3_port: int = 9000
    s3_bucket: str = "roadbuilders"

    elasticsearch_host: str = "localhost"
    elasticsearch_port: int = 9200
    elasticsearch_index: str = "roadbuilders_text"

    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dim: int = 512

    cross_encoder_model: str = "cohere/rerank-v3.5"

    openrouter_api_key: str | None = None
    anthropic_api_key: str | None = None
    jwt_secret: str | None = None

    openrouter_api_url_chat: str = "https://openrouter.ai/api/v1/chat/completions"
    openrouter_api_url_rerank: str = "https://openrouter.ai/api/v1/rerank"
    openrouter_api_url_embedding: str = "https://openrouter.ai/api/v1/embeddings"

    multi_query_model: str = "anthropic/claude-sonnet-4.6"
    multi_query_n: int = 5
    retriever_candidate_k: int = 50
    retriever_top_k: int = 10

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def auth_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}_auth"
        )

    @property
    def test_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}_test"
        )

    @property
    def elasticsearch_url(self) -> str:
        return f"http://{self.elasticsearch_host}:{self.elasticsearch_port}"

    @property
    def s3_endpoint(self) -> str:
        return f"http://{self.s3_host}:{self.s3_port}"

    @property
    def s3_access_key(self) -> str:
        return self.minio_root_user

    @property
    def s3_secret_key(self) -> str:
        return self.minio_root_password


settings = Settings()  # type: ignore[call-arg]
