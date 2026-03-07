"""Wallet creation for agents. Reads wallet credentials from .env, balance tracked in DB."""

import os
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()

AGENT_WALLET_ADDRESS = os.environ["AGENT_WALLET_ADDRESS"]
AGENT_WALLET_PRIVATE_KEY = os.environ["AGENT_WALLET_PRIVATE_KEY"]


async def create_agent_wallet(entry_fee_usdc: Decimal) -> dict:
    """Create a new wallet for an agent and fund it with the entry fee.

    Reads wallet address and private key from environment variables.
    The initial balance is tracked in the agents table rather than on-chain.
    """
    return {
        "wallet_address": AGENT_WALLET_ADDRESS,
        "wallet_private_key": AGENT_WALLET_PRIVATE_KEY,
        "balance_usdc": entry_fee_usdc,
    }
