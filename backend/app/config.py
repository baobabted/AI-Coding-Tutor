from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    jwt_secret_key: str
    jwt_access_token_expire_minutes: int
    jwt_refresh_token_expire_days: int
    cors_origins: list[str]

    # LLM settings (Phase 2)
    llm_provider: str
    anthropic_api_key: str
    openai_api_key: str
    google_api_key: str

    # Embedding settings (Phase 2)
    embedding_provider: str
    cohere_api_key: str
    voyageai_api_key: str

    # Token limits (Phase 2)
    llm_max_context_tokens: int
    llm_max_user_input_tokens: int
    context_compression_threshold: float
    user_daily_input_token_limit: int
    user_daily_output_token_limit: int

    # Upload settings (Phase 2B)
    upload_storage_dir: str
    upload_expiry_hours: int
    upload_max_images_per_message: int
    upload_max_documents_per_message: int
    upload_max_image_mb: int
    upload_max_document_mb: int
    upload_max_document_tokens: int

    class Config:
        env_file = ".env"


settings = Settings()
