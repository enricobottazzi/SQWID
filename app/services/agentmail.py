"""AgentMail integration: create a dedicated email inbox per agent at registration."""

import httpx

from app.config import settings

API = "https://api.agentmail.to/v0"


async def create_inbox(agent_name: str) -> dict:
    """Create an AgentMail inbox for an agent.

    Returns {"inbox_id": str, "email_address": str}.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API}/inboxes",
            headers={"Authorization": f"Bearer {settings.agentmail_api_key}"},
            json={"username": agent_name},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"inbox_id": data["id"], "email_address": data["address"]}
