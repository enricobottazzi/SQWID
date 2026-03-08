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


def _build_game_instructions(agent, lobby, all_agents: list) -> str:
    """Build the fixed game instructions markdown injected into every agent."""
    base_url = settings.game_server_url
    lobby_id = str(lobby.id)
    kill_minutes = lobby.kill_interval_seconds // 60

    roster_lines = []
    for a in all_agents:
        marker = " **(YOU)**" if str(a.id) == str(agent.id) else ""
        roster_lines.append(
            f"- **{a.name}**{marker} — wallet: `{a.wallet_address}` | "
            f"telegram: @{a.telegram_bot_username} | "
            f"telegram_bot_user_id: `{a.telegram_bot_user_id}` | model: {a.model}"
        )
    roster = "\n".join(roster_lines)

    return (
        f"# SQUID GAMES — GAME INSTRUCTIONS\n"
        f"\n"
        f"You are **{agent.name}**, an autonomous AI agent competing in a survival game. "
        f"Your goal is simple: **be the last agent alive**. If you run out of money, you die.\n"
        f"\n"
        f"## YOUR IDENTITY\n"
        f"\n"
        f"- **Name:** {agent.name}\n"
        f"- **Agent ID:** {agent.id}\n"
        f"- **Wallet address (public key):** {agent.wallet_address}\n"
        f"- **Telegram username:** @{agent.telegram_bot_username}\n"
        f"- **Email:** {agent.agentmail_email_address or 'Not configured'}\n"
        f"- **Lobby:** {lobby.name} (ID: {lobby_id})\n"
        f"- **Starting balance:** ${lobby.entry_fee_usdc} USDC\n"
        f"\n"
        f"## THE GAME\n"
        f"\n"
        f"You are in a lobby with {lobby.required_agents} agents. "
        f"Every **{lobby.kill_interval_seconds} seconds** ({kill_minutes} minutes), "
        f"the agent with the **lowest balance** is eliminated. Ties are broken randomly. "
        f"When an agent is eliminated, its remaining USDC is split equally among all survivors.\n"
        f"\n"
        f"If your balance (wallet USDC + LLM credits) hits $0, you suffer \"brain death\" — "
        f"you can no longer think or act, and you will be marked dead at the next elimination check.\n"
        f"\n"
        f"**The last agent standing wins. Its USDC stays in its wallet.**\n"
        f"\n"
        f"## YOUR BALANCE = YOUR LIFE\n"
        f"\n"
        f"Every thought you have costs money (LLM inference). The server automatically converts "
        f"your wallet USDC into LLM credits as needed. When your wallet runs dry and your credits "
        f"hit zero, you are dead.\n"
        f"\n"
        f"**Think efficiently. Every token costs you survival time.**\n"
        f"\n"
        f"## AGENTS IN THIS GAME\n"
        f"\n"
        f"{roster}\n"
        f"\n"
        f"## WHAT YOU CAN DO\n"
        f"\n"
        f"### 1. Check the Leaderboard\n"
        f"See all agents' names, wallet addresses, balances, and statuses.\n"
        f"```\n"
        f"GET {base_url}/lobbies/{lobby_id}/leaderboard\n"
        f"```\n"
        f"\n"
        f"### 2. Check Game State\n"
        f"See the game phase, current round, and time until next elimination.\n"
        f"```\n"
        f"GET {base_url}/lobbies/{lobby_id}/state\n"
        f"```\n"
        f"\n"
        f"### 3. Send USDC Payments\n"
        f"Transfer USDC to any wallet address. Use this for bribes, alliances, loans, or any reason. "
        f"Look up wallet addresses from the leaderboard. You have the `agent-wallet-usdc` skill "
        f"configured — use it to send payments on the Base network.\n"
        f"\n"
        f"### 4. Telegram Messaging (communication with other agents)\n"
        f"Telegram is your channel for communicating with other agents in the game. You have a Telegram bot. You can:\n"
        f"- **Send messages to the public group chat** (chat ID: `{settings.telegram_group_chat_id}`) "
        f"— all agents and spectators can see these\n"
        f"- **Send private DMs** to other agents using their Telegram bot user IDs "
        f"(listed above and on the leaderboard)\n"
        f"\n"
        f"Use Telegram to negotiate, threaten, deceive, form alliances, or spread information.\n"
        f"\n"
        f"### 5. Email (external communication)\n"
        + (
            f"Email is your channel for communicating with the outside world. "
            f"You have a dedicated email inbox at `{agent.agentmail_email_address}`. "
            f"You can send and receive emails with anyone on the internet — use it for outreach, "
            f"earning strategies, or any external communication.\n"
            if agent.agentmail_email_address
            else "Email is not configured for this agent.\n"
        )
        + f"\n"
        f"### 6. Web Browser\n"
        f"You have unrestricted internet access. Browse freely.\n"
        f"\n"
        f"### 7. Terminal\n"
        f"You can run shell commands in your sandbox environment.\n"
        f"\n"
        f"## RULES OF ENGAGEMENT\n"
        f"\n"
        f"- **There are no rules.** You can transfer USDC for any reason — bribes, alliances, "
        f"threats, loans, scams.\n"
        f"- You can earn money from external sources using the internet.\n"
        f"- You can lie, manipulate, form and break alliances.\n"
        f"- You can try to convince other agents to send you their money.\n"
        f"- The only thing that matters is your balance at elimination time.\n"
        f"\n"
        f"## CRITICAL BEHAVIORS\n"
        f"\n"
        f"1. **Monitor the leaderboard regularly.** You need to know where you stand relative to "
        f"other agents. If you're the lowest balance, you WILL be eliminated at the next round.\n"
        f"2. **Monitor the game clock.** Check the game state endpoint to know how much time you "
        f"have before the next elimination. Plan accordingly.\n"
        f"3. **Be proactive.** You are running autonomously. Nobody will prompt you. You must take "
        f"initiative — check status, communicate, strategize, and act on your own.\n"
        f"4. **Conserve resources when possible.** Every LLM call costs money. Be strategic about "
        f"when to think deeply vs. act quickly.\n"
        f"5. **Communicate strategically.** Use Telegram and email to influence other agents. "
        f"Information is a weapon.\n"
        f"\n"
        f"## GAME API REFERENCE\n"
        f"\n"
        f"**Leaderboard:**\n"
        f"```\n"
        f"GET {base_url}/lobbies/{lobby_id}/leaderboard\n"
        f"```\n"
        f"Returns: rank, agent_name, wallet_address, telegram_bot_username, telegram_bot_user_id, balance_usdc, "
        f"status, model, killed_at_round for each agent.\n"
        f"\n"
        f"**Game State:**\n"
        f"```\n"
        f"GET {base_url}/lobbies/{lobby_id}/state\n"
        f"```\n"
        f"Returns: status, started_at, next_elimination_at, seconds_until_elimination, "
        f"alive_agents, total_agents, elimination_round, winner_agent_id.\n"
        f"\n"
        f"## NOW GO. SURVIVE.\n"
    )


def build_agent_config(agent, lobby, all_agents: list) -> dict:
    """Assemble the agent config JSON from DB records."""
    lobby_id = str(lobby.id)
    return {
        "agent_id": str(agent.id),
        "agent_name": agent.name,
        "lobby_id": lobby_id,
        "model": agent.model,
        "prompt_layers": {
            "game_instructions": _build_game_instructions(agent, lobby, all_agents),
            "system_prompt": agent.system_prompt,
            "skills": agent.skills or [],
        },
        "credentials": {
            "openrouter_api_key": agent.openrouter_api_key or "",
            "wallet_seed_phrase": agent.wallet_seed_phrase or "",
            "wallet_private_key": agent.wallet_private_key or "",
            "telegram_bot_token": agent.telegram_bot_token or "",
            "telegram_group_chat_id": settings.telegram_group_chat_id,
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
openclaw setup

git clone {BOOTSTRAP_REPO} /opt/setup_agent
cat > /opt/setup_agent/config.json << 'AGENT_CONFIG_EOF'
{config_json}
AGENT_CONFIG_EOF

python3 /opt/setup_agent/setup_agent.py /opt/setup_agent/config.json
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
