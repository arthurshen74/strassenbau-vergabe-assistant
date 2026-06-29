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
    langchain_index: str = "idx-langchain-roadbuilders"

    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dim: int = 512
    embedding_cache_enabled: bool = True

    cross_encoder_model: str = "cohere/rerank-4-fast"

    openrouter_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_static_maps_api_key: str | None = None
    jwt_secret: str | None = None

    # Default zoom for the render_map chat tool. 12 frames roughly a 3 km radius at German
    # latitudes on the 800px image; higher zooms in. The model may override per call.
    static_map_zoom: int = 12

    # Google Maps Platform endpoints behind the calculator's Baustelle geocoding and supplier
    # road distances. They reuse the same key as the static map tool (google_static_maps_api_key):
    # the Geocoding API resolves the Baubeschreibung to lat/lon, the Routes API computeRouteMatrix
    # ranks N candidate suppliers by road distance in one call.
    google_maps_geocoding_url: str = "https://maps.googleapis.com/maps/api/geocode/json"
    google_maps_route_matrix_url: str = (
        "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
    )
    maps_request_timeout_seconds: float = 20.0

    openrouter_api_url_chat: str = "https://openrouter.ai/api/v1/chat/completions"
    openrouter_api_url_rerank: str = "https://openrouter.ai/api/v1/rerank"
    openrouter_api_url_embedding: str = "https://openrouter.ai/api/v1/embeddings"

    multi_query_n: int = 5
    retriever_candidate_k: int = 50
    retriever_top_k: int = 10

    # EKT calculator agent: the OpenRouter model behind its three LLM sites, and the
    # offline mock toggle (canned replies, wired to the FSS demo position).
    calculator_model: str = "openai/gpt-5.4"
    calculator_mock: bool = False
    # OpenRouter reasoning effort for the calculator's LLM sites; None disables the
    # reasoning request (and the provider reasoning summaries in the output).
    calculator_reasoning_effort: str | None = "low"
    # Min BM25 separation confidence to AUTO-apply a matched Baustoff at Gate A; below this
    # the top hit is surfaced for the Kalkulator to confirm/choose (HITL). Range (0.5, 1].
    calculator_baustoff_match_threshold: float = 0.6
    # Target machine deployment window (hours) for right-sizing the default machine: the
    # default is the smallest candidate whose capacity clears the job within this window.
    calculator_maschine_zielstunden: float = 16.0

    # Phoenix HTTP OTLP collector (the docker-compose `phoenix` service).
    phoenix_collector_endpoint: str = "http://localhost:6006/v1/traces"

    worker_poll_interval_seconds: float = 2.0
    worker_lease_seconds: float = 60.0
    worker_max_attempts: int = 3
    ingest_status_poll_interval_seconds: float = 1.5

    # Ingestion activity stream: emit one activity line every N units of work (the live console
    # feed and the worker's lease heartbeat), flush buffered lines this often (keep well below
    # worker_lease_seconds), and prune lines older than the retention window.
    activity_thumbnail_every: int = 10
    activity_embed_every: int = 10
    activity_lv_item_every: int = 1
    activity_flush_seconds: float = 1.0
    activity_retention_hours: int = 24

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
