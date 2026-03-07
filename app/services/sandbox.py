"""DigitalOcean Droplet sandbox management for agents."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DO_API = "https://api.digitalocean.com/v2"
DROPLET_SIZE = "s-1vcpu-2gb"
DROPLET_IMAGE = "ubuntu-22-04-x64"
DROPLET_REGION = "lon1"
HTTP_TIMEOUT = 30

CLOUD_INIT = """\
#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive

while fuser /var/lib/apt/lists/lock /var/lib/dpkg/lock /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
    sleep 5
done

curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs
export NODE_OPTIONS="--max-old-space-size=1536"
npm install -g openclaw
"""


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.do_api_token}",
        "Content-Type": "application/json",
    }


async def launch_sandbox(agent_id: str, agent_name: str) -> dict:
    """Create a droplet for an agent. Returns {"droplet_id": int}."""
    slug = f"sqwid-{agent_id}-{agent_name.lower().replace(' ', '-')}"[:63]
    payload = {
        "name": slug,
        "region": DROPLET_REGION,
        "size": DROPLET_SIZE,
        "image": DROPLET_IMAGE,
        "ssh_keys": [settings.do_ssh_key_id] if settings.do_ssh_key_id else [],
        "tags": ["sqwid", f"agent-{agent_id}"],
        "user_data": CLOUD_INIT,
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
