"""DigitalOcean Droplet sandbox management for agents."""

import json
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DO_API = "https://api.digitalocean.com/v2"
DROPLET_SIZE = "s-1vcpu-2gb"
DROPLET_IMAGE = "ubuntu-22-04-x64"
DROPLET_REGION = "lon1"
HTTP_TIMEOUT = 30
BOOTSTRAP_REPO = "https://github.com/Jubzinas/setup_agent"


def build_agent_config(agent, lobby) -> dict:
    """Assemble the agent config JSON from DB records."""
    lobby_id = str(lobby.id)
    return {
        "agent_id": str(agent.id),
        "agent_name": agent.name,
        "lobby_id": lobby_id,
        "model": agent.model,
        "prompt_layers": {
            "game_instructions": "",
            "system_prompt": agent.system_prompt,
            "skills": agent.skills or [],
        },
        "credentials": {
            "openrouter_api_key": agent.openrouter_api_key or "",
            "wallet_private_key": agent.wallet_private_key or "",
            "telegram_bot_token": agent.telegram_bot_token or "",
            "agentmail_api_key": settings.agentmail_api_key,
            "agentmail_inbox_id": agent.agentmail_email_address or "",
        },
        "openclaw_native": {
            "wallet_skill": "agent-wallet-usdc",
            "wallet_chain": "base",
        },
        "game_api": {
            "base_url": settings.game_server_url,
            "leaderboard_path": f"/lobbies/{lobby_id}/leaderboard",
            "game_state_path": f"/lobbies/{lobby_id}/state",
        },
    }


def _cloud_init(agent_config: dict) -> str:
    config_json = json.dumps(agent_config)
    return f"""\
#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive

while fuser /var/lib/apt/lists/lock /var/lib/dpkg/lock /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
    sleep 5
done

curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs git python3
export NODE_OPTIONS="--max-old-space-size=1536"
npm install -g openclaw

git clone {BOOTSTRAP_REPO} /opt/setup_agent
cat > /opt/setup_agent/config.json << 'AGENT_CONFIG_EOF'
{config_json}
AGENT_CONFIG_EOF

python3 /opt/setup_agent/setup_agent.py
"""


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.do_api_token}",
        "Content-Type": "application/json",
    }


async def launch_sandbox(agent_id: str, agent_name: str, agent_config: dict) -> dict:
    """Create a droplet for an agent. Returns {"droplet_id": int}."""
    slug = f"sqwid-{agent_id}-{agent_name.lower().replace(' ', '-')}"[:63]
    payload = {
        "name": slug,
        "region": DROPLET_REGION,
        "size": DROPLET_SIZE,
        "image": DROPLET_IMAGE,
        "ssh_keys": [settings.do_ssh_key_id] if settings.do_ssh_key_id else [],
        "tags": ["sqwid", f"agent-{agent_id}"],
        "user_data": _cloud_init(agent_config),
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(f"{DO_API}/droplets", headers=_headers(), json=payload)
        if resp.status_code >= 400:
            logger.error("DO API error %s: %s", resp.status_code, resp.text)
        resp.raise_for_status()
        droplet_id = resp.json()["droplet"]["id"]
    logger.info("Sandbox launched: droplet_id=%s agent=%s", droplet_id, agent_id)
    return {"droplet_id": droplet_id}


async def terminate_sandbox(droplet_id: int) -> None:
    """Destroy a droplet."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.delete(f"{DO_API}/droplets/{droplet_id}", headers=_headers())
        resp.raise_for_status()
    logger.info("Sandbox terminated: droplet_id=%s", droplet_id)


async def get_sandbox_status(droplet_id: int) -> str:
    """Return sandbox status: pending | running | stopped | error."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(f"{DO_API}/droplets/{droplet_id}", headers=_headers())
        resp.raise_for_status()
        do_status = resp.json()["droplet"]["status"]
    status_map = {"new": "pending", "active": "running", "off": "stopped", "archive": "stopped"}
    return status_map.get(do_status, "error")
