"""Application settings loaded from environment variables."""

from decimal import Decimal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/squid_games"
    openrouter_provisioning_key: str = ""
    telegram_master_bot_token: str = ""
    telegram_group_chat_id: str = ""
    agentmail_api_key: str = ""
    agentmail_pod_id: str = ""
    credit_threshold: Decimal = Decimal("0.50")
    credit_topup_amount: Decimal = Decimal("1.00")
    do_api_token: str = ""
    do_ssh_key_id: str = ""
    game_server_url: str = ""
    base_rpc_url: str = "https://mainnet.base.org"
    game_wallet_address: str = ""
    game_wallet_private_key: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
