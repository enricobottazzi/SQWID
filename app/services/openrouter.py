"""OpenRouter API key provisioning and credit balance queries."""

from decimal import Decimal

import httpx

from app.config import settings

BASE_URL = "https://openrouter.ai/api/v1"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.openrouter_provisioning_key}"}


async def create_api_key(agent_name: str) -> dict:
    """Provision a new per-agent API key. Returns {"key": ..., "hash": ...}."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/keys",
            headers=_headers(),
            json={"name": f"squid-{agent_name}", "limit": 0},
        )
        resp.raise_for_status()
        body = resp.json()
        return {"key": body["key"], "hash": body["data"]["hash"]}


async def get_credit_balance(key_hash: str) -> Decimal:
    """Return remaining credit (limit_remaining) for a provisioned key."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/keys/{key_hash}",
            headers=_headers(),
        )
        resp.raise_for_status()
        remaining = resp.json()["data"]["limit_remaining"]
        return Decimal(str(remaining)) if remaining is not None else Decimal("0")


async def increase_spending_limit(key_hash: str, amount: Decimal) -> None:
    """Increase a sub-key's spending limit by *amount* dollars."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/keys/{key_hash}", headers=_headers())
        resp.raise_for_status()
        current_limit = resp.json()["data"]["limit"] or 0
        resp = await client.patch(
            f"{BASE_URL}/keys/{key_hash}",
            headers=_headers(),
            json={"limit": current_limit + float(amount)},
        )
        resp.raise_for_status()
