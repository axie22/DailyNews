from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://mlnews:mlnews@localhost:5432/mlnews"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    pipeline_interval_hours: int = 6
    log_level: str = "INFO"
    x_bearer_token: str = ""
    x_monthly_tweet_cap: int = 10000


settings = Settings()
