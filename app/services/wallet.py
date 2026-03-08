"""Wallet management via access-code-to-wallet mapping from environment variables."""

import os
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()

WalletInfo = dict[str, str | Decimal]

_ACCESS_CODE_WALLETS: dict[str, dict[str, str]] = {}

for i in range(1, 4):
    code = os.environ.get(f"AGENT_{i}_ACCESS_CODE")
    address = os.environ.get(f"AGENT_{i}_WALLET_ADDRESS")
    private_key = os.environ.get(f"AGENT_{i}_WALLET_PRIVATE_KEY")
    seed_phrase = os.environ.get(f"AGENT_{i}_WALLET_SEED_PHRASE")
    telegram_bot_token = os.environ.get(f"AGENT_{i}_TELEGRAM_BOT_TOKEN", "")
    if code and address and private_key and seed_phrase:
        _ACCESS_CODE_WALLETS[code] = {
            "wallet_address": address,
            "wallet_private_key": private_key,
            "wallet_seed_phrase": seed_phrase,
            "telegram_bot_token": telegram_bot_token,
        }


def validate_access_code(access_code: str) -> bool:
    return access_code in _ACCESS_CODE_WALLETS


def get_wallet_by_access_code(access_code: str, entry_fee_usdc: Decimal) -> WalletInfo:
    """Look up the pre-funded wallet for a given access code.

    Raises KeyError if the access code is invalid.
    """
    wallet = _ACCESS_CODE_WALLETS[access_code]
    return {
        "wallet_address": wallet["wallet_address"],
        "wallet_private_key": wallet["wallet_private_key"],
        "wallet_seed_phrase": wallet["wallet_seed_phrase"],
        "telegram_bot_token": wallet["telegram_bot_token"],
        "balance_usdc": entry_fee_usdc,
    }
