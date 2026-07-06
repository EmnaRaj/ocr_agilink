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

    # Chatbot copilot — a TEXT, tool-calling LLM (NOT a VLM). It answers over the
    # already-extracted structured data, never images, so it is configured
    # independently of the VLM. chat_base_url/chat_api_key fall back to the vllm_*
    # connection only for backward compatibility when CHAT_* is unset (see
    # app/agent/model.py).
    # Primary: qwen3-30b-a3b (cheap, strong multilingual + tool-calling).
    # Fallback if it underperforms: google/gemini-2.5-flash-lite.
    chat_model: str = "qwen/qwen3-30b-a3b-instruct-2507"
    chat_base_url: str | None = None
    chat_api_key: str | None = None

    api_secret_key: str
    environment: str = "development"

    # --- SharePoint auto-ingest (Microsoft Graph delta poller) ---
    # When enabled, a Celery-beat task polls a SharePoint folder every
    # sharepoint_poll_seconds and feeds any NEW pdf into the same pipeline as a
    # manual upload. App-only auth (client credentials) — needs an Azure AD app
    # registration with Files.Read.All / Sites.Read.All (admin-consented).
    sharepoint_enabled: bool = False
    sharepoint_tenant_id: str | None = None
    sharepoint_client_id: str | None = None
    sharepoint_client_secret: str | None = None
    # Either the site id (…/sites/{site-id}) OR leave blank and set the drive id.
    sharepoint_site_id: str | None = None
    sharepoint_drive_id: str | None = None
    # Folder to watch, relative to the drive root (e.g. "Scans/Fiches"); blank = root.
    sharepoint_folder_path: str = ""
    sharepoint_poll_seconds: int = 180

    # --- Local drop-folder auto-ingest ---
    # A filesystem version of the SharePoint poller: drop PDFs/images into this
    # folder (mounted into the worker/beat container) and they're uploaded +
    # scanned automatically. Processed files are moved to <dir>/processed/.
    local_inbox_enabled: bool = False
    local_inbox_dir: str = "/srv/inbox"
    local_inbox_poll_seconds: int = 30

    # Comma-separated list of allowed SPA origins (CORS); "*" allows any.
    cors_origins_raw: str = "*"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]


settings = Settings()
