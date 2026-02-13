from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    jwt_secret_key: str
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    cors_origins: list[str] = ["http://localhost:5173"]

    # LLM settings (Phase 2)
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""

    # Embedding settings (Phase 2)
    embedding_provider: str = "cohere"
    cohere_api_key: str = ""
    voyageai_api_key: str = ""

    # Token limits (Phase 2)
    llm_max_context_tokens: int = 10000
    context_compression_threshold: float = 0.8
    user_daily_input_token_limit: int = 50000
    user_daily_output_token_limit: int = 50000

    class Config:
        env_file = ".env"


settings = Settings()
