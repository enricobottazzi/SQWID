"""Wallet creation for agents. Stubbed — generates fake addresses, balance tracked in DB."""

import uuid
from decimal import Decimal


async def create_agent_wallet(entry_fee_usdc: Decimal) -> dict:
    """Create a new wallet for an agent and fund it with the entry fee.

    Stub: generates a random address/key pair. The initial balance is
    tracked in the agents table rather than on-chain.
    """
    return {
        "wallet_address": f"0x{uuid.uuid4().hex[:40]}",
        "wallet_private_key": f"0x{uuid.uuid4().hex}",
        "balance_usdc": entry_fee_usdc,
    }
