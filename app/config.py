"""Application settings loaded from environment variables."""

from decimal import Decimal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/squid_games"
    openrouter_provisioning_key: str = ""
    discord_master_bot_token: str = ""
    agentmail_api_key: str = ""
    credit_threshold: Decimal = Decimal("0.50")
    credit_topup_amount: Decimal = Decimal("1.00")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
