"""Discord integration: bot validation at registration, guild setup at game start."""

import httpx

from app.config import settings

API = "https://discord.com/api/v10"


async def validate_bot_token(bot_token: str) -> dict:
    """Validate a bot token and return its user profile.

    Returns {"discord_token": str, "discord_user_id": str}.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API}/users/@me",
            headers={"Authorization": f"Bot {bot_token}"},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"discord_token": bot_token, "discord_user_id": data["id"]}


async def setup_game_guild(lobby_name: str, agent_bot_tokens: list[str]) -> dict:
    """Create a Discord guild for the lobby, with #town-square and spectator role.

    The master bot creates the guild, then each agent bot is added via invite.
    Returns {"guild_id": str, "channel_id": str, "invite_url": str}.
    """
    headers = {"Authorization": f"Bot {settings.discord_master_bot_token}"}

    async with httpx.AsyncClient() as client:
        # Create guild
        guild_resp = await client.post(
            f"{API}/guilds", headers=headers, json={"name": lobby_name},
        )
        guild_resp.raise_for_status()
        guild = guild_resp.json()
        guild_id = guild["id"]

        # Find the default #general channel created with the guild
        channels_resp = await client.get(
            f"{API}/guilds/{guild_id}/channels", headers=headers,
        )
        channels_resp.raise_for_status()
        text_channels = [c for c in channels_resp.json() if c["type"] == 0]

        # Rename first text channel to town-square, or create one
        if text_channels:
            ch = text_channels[0]
            await client.patch(
                f"{API}/channels/{ch['id']}", headers=headers,
                json={"name": "town-square"},
            )
            channel_id = ch["id"]
        else:
            ch_resp = await client.post(
                f"{API}/guilds/{guild_id}/channels", headers=headers,
                json={"name": "town-square", "type": 0},
            )
            ch_resp.raise_for_status()
            channel_id = ch_resp.json()["id"]

        # Create read-only spectator role (deny SEND_MESSAGES = 0x800)
        role_resp = await client.post(
            f"{API}/guilds/{guild_id}/roles", headers=headers,
            json={"name": "spectator", "permissions": "0"},
        )
        role_resp.raise_for_status()

        # Create invite for spectators
        invite_resp = await client.post(
            f"{API}/channels/{channel_id}/invites", headers=headers,
            json={"max_age": 0, "max_uses": 0},
        )
        invite_resp.raise_for_status()
        invite_code = invite_resp.json()["code"]

        # Have each agent bot join the guild via invite
        for token in agent_bot_tokens:
            await client.post(
                f"{API}/invites/{invite_code}",
                headers={"Authorization": f"Bot {token}"},
            )

    return {
        "guild_id": guild_id,
        "channel_id": channel_id,
        "invite_url": f"https://discord.gg/{invite_code}",
    }
