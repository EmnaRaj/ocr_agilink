from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str

    minio_endpoint: str
    minio_root_user: str
    minio_root_password: str
    minio_bucket: str
    minio_use_ssl: bool = False

    vlm_backend: str = "groq"
    groq_api_key: str | None = None
    groq_model: str | None = None
    vllm_base_url: str | None = None
    vllm_model: str | None = None
    vllm_api_key: str | None = None

    # Chatbot (text-to-SQL assistant) — a text model on the OpenRouter endpoint.
    chat_model: str = "google/gemini-2.5-flash"

    api_secret_key: str
    environment: str = "development"

    # Comma-separated list of allowed SPA origins (CORS); "*" allows any.
    cors_origins_raw: str = "*"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]


settings = Settings()
