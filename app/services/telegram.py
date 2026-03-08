"""Telegram integration: bot validation at registration, group chat setup at game start.

Bot API limitations: bots cannot create group chats. The master bot must be
manually added as admin to a pre-created group, OR group creation is handled
via the Telegram Client API (MTProto/TDLib) using a user account. For the demo,
we use a pre-created group whose chat_id is set in TELEGRAM_GROUP_CHAT_ID.
"""

import httpx

from app.config import settings

API = "https://api.telegram.org"


async def validate_bot_token(bot_token: str) -> dict:
    """Validate a bot token via getMe and return its profile.

    Returns {"telegram_bot_token": str, "telegram_bot_user_id": str, "telegram_bot_username": str}.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API}/bot{bot_token}/getMe")
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise ValueError(f"Telegram getMe failed: {data}")
    return {
        "telegram_bot_token": bot_token,
        "telegram_bot_user_id": str(data["result"]["id"]),
        "telegram_bot_username": data["result"].get("username", ""),
    }


async def setup_game_group(lobby_name: str, agent_bot_tokens: list[str]) -> dict:
    """Set up the Telegram group for a game lobby.

    Uses a pre-created group (TELEGRAM_GROUP_CHAT_ID). The master bot:
    1. Renames the group to the lobby name
    2. Restricts the group so regular members (spectators) are read-only
    3. Promotes each agent bot to admin so they can still post
    4. Generates a fresh invite link for spectators

    Returns {"group_chat_id": str, "invite_url": str}.
    """
    master_token = settings.telegram_master_bot_token
    group_chat_id = settings.telegram_group_chat_id
    master_url = f"{API}/bot{master_token}"

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{master_url}/setChatTitle",
            json={"chat_id": group_chat_id, "title": lobby_name},
        )

        # Lock the group: spectators (regular members) can only read
        await client.post(
            f"{master_url}/setChatPermissions",
            json={
                "chat_id": group_chat_id,
                "permissions": {
                    "can_send_messages": False,
                    "can_send_audios": False,
                    "can_send_documents": False,
                    "can_send_photos": False,
                    "can_send_videos": False,
                    "can_send_video_notes": False,
                    "can_send_voice_notes": False,
                    "can_send_polls": False,
                    "can_send_other_messages": False,
                    "can_add_web_page_previews": False,
                    "can_change_info": False,
                    "can_invite_users": False,
                    "can_pin_messages": False,
                    "can_manage_topics": False,
                },
            },
        )

        # Promote each agent bot to admin so they bypass the restriction
        for token in agent_bot_tokens:
            bot_resp = await client.get(f"{API}/bot{token}/getMe")
            bot_resp.raise_for_status()
            bot_user_id = bot_resp.json()["result"]["id"]
            await client.post(
                f"{master_url}/promoteChatMember",
                json={
                    "chat_id": group_chat_id,
                    "user_id": bot_user_id,
                    "can_post_messages": True,
                    "can_edit_messages": True,
                    "can_delete_messages": True,
                    "can_manage_chat": True,
                    "can_invite_users": True,
                    "can_restrict_members": False,
                    "can_promote_members": False,
                    "can_change_info": False,
                    "can_pin_messages": True,
                },
            )

        invite_resp = await client.post(
            f"{master_url}/exportChatInviteLink",
            json={"chat_id": group_chat_id},
        )
        invite_resp.raise_for_status()
        invite_url = invite_resp.json()["result"]

    return {
        "group_chat_id": str(group_chat_id),
        "invite_url": invite_url,
    }
