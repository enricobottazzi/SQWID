"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/squid_games"
    openrouter_api_key: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
