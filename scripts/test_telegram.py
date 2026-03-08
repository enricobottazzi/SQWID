#!/usr/bin/env python3
"""Smoke-test real Telegram bot tokens from .env against the Telegram Bot API.

Usage:
    source .venv/bin/activate
    python scripts/test_telegram.py
"""

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

API = "https://api.telegram.org"


def check_bot(label: str, token: str) -> bool:
    """Call getMe and print the result. Returns True on success."""
    if not token or token.startswith("your-"):
        print(f"  [{label}] SKIPPED — no real token set")
        return False
    resp = httpx.get(f"{API}/bot{token}/getMe")
    if resp.status_code != 200:
        print(f"  [{label}] FAILED — HTTP {resp.status_code}: {resp.text[:200]}")
        return False
    data = resp.json()
    if not data.get("ok"):
        print(f"  [{label}] FAILED — API error: {data}")
        return False
    bot = data["result"]
    print(f"  [{label}] OK — @{bot.get('username')} (id={bot['id']}, name={bot.get('first_name', '?')})")
    return True


def test_group_chat(master_token: str, group_chat_id: str, agent_tokens: list[str]) -> bool:
    """Test that the master bot can interact with the pre-created group."""
    if not group_chat_id or group_chat_id.startswith("your-"):
        print("  SKIPPED — TELEGRAM_GROUP_CHAT_ID not set")
        return False

    # Check master bot can read the group
    resp = httpx.post(
        f"{API}/bot{master_token}/getChat",
        json={"chat_id": group_chat_id},
    )
    if resp.status_code != 200 or not resp.json().get("ok"):
        print(f"  FAILED — master bot cannot access group: {resp.text[:200]}")
        print("  Make sure the master bot is a member (and admin) of the group.")
        return False

    chat = resp.json()["result"]
    print(f"  Group found: \"{chat.get('title', '?')}\" (type={chat.get('type')})")

    # Test renaming
    rename_resp = httpx.post(
        f"{API}/bot{master_token}/setChatTitle",
        json={"chat_id": group_chat_id, "title": "smoke-test-rename"},
    )
    if rename_resp.status_code == 200 and rename_resp.json().get("ok"):
        print("  setChatTitle OK")
        # Rename back
        httpx.post(
            f"{API}/bot{master_token}/setChatTitle",
            json={"chat_id": group_chat_id, "title": chat.get("title", "game-lobby")},
        )
    else:
        print(f"  setChatTitle FAILED (master bot may not be admin): {rename_resp.text[:200]}")

    # Lock the group: spectators (regular members) can only read
    perms_resp = httpx.post(
        f"{API}/bot{master_token}/setChatPermissions",
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
    if perms_resp.status_code == 200 and perms_resp.json().get("ok"):
        print("  setChatPermissions OK — group is now read-only for spectators")
    else:
        print(f"  setChatPermissions FAILED: {perms_resp.text[:200]}")

    # Promote each agent bot to admin so they can still post
    for i, token in enumerate(agent_tokens, 1):
        if not token or token.startswith("your-"):
            continue
        bot_resp = httpx.get(f"{API}/bot{token}/getMe")
        if bot_resp.status_code != 200:
            continue
        bot_user_id = bot_resp.json()["result"]["id"]
        promote_resp = httpx.post(
            f"{API}/bot{master_token}/promoteChatMember",
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
        if promote_resp.status_code == 200 and promote_resp.json().get("ok"):
            print(f"  Agent {i} promoted to admin OK")
        else:
            print(f"  Agent {i} promote FAILED: {promote_resp.text[:200]}")

    # Test invite link
    invite_resp = httpx.post(
        f"{API}/bot{master_token}/exportChatInviteLink",
        json={"chat_id": group_chat_id},
    )
    if invite_resp.status_code == 200 and invite_resp.json().get("ok"):
        print(f"  Invite link: {invite_resp.json()['result']}")
    else:
        print(f"  exportChatInviteLink FAILED: {invite_resp.text[:200]}")

    # Test that agent bots (now admins) can send messages in the locked group
    for i, token in enumerate(agent_tokens, 1):
        if not token or token.startswith("your-"):
            continue
        msg_resp = httpx.post(
            f"{API}/bot{token}/sendMessage",
            json={"chat_id": group_chat_id, "text": f"Smoke test from Agent {i}"},
        )
        if msg_resp.status_code == 200 and msg_resp.json().get("ok"):
            print(f"  Agent {i} sent message in locked group OK")
            msg_id = msg_resp.json()["result"]["message_id"]
            httpx.post(
                f"{API}/bot{token}/deleteMessage",
                json={"chat_id": group_chat_id, "message_id": msg_id},
            )
        else:
            print(f"  Agent {i} message FAILED: {msg_resp.text[:200]}")

    return True


def main():
    print("=== Telegram Bot Token Smoke Test ===\n")

    master_token = os.environ.get("TELEGRAM_MASTER_BOT_TOKEN", "")
    group_chat_id = os.environ.get("TELEGRAM_GROUP_CHAT_ID", "")
    agent_tokens = [
        os.environ.get(f"AGENT_{i}_TELEGRAM_BOT_TOKEN", "")
        for i in range(1, 4)
    ]

    tokens = {
        "MASTER BOT": master_token,
        "AGENT 1 BOT": agent_tokens[0],
        "AGENT 2 BOT": agent_tokens[1],
        "AGENT 3 BOT": agent_tokens[2],
    }

    print("--- Bot token validation (getMe) ---")
    results = {}
    for label, token in tokens.items():
        results[label] = check_bot(label, token)

    ok_count = sum(results.values())
    total = len(results)
    print(f"\n{ok_count}/{total} bots validated.\n")

    if ok_count == 0:
        print("No valid tokens found. See instructions below to create them.\n")
        _print_setup_instructions()
        sys.exit(1)

    if results["MASTER BOT"]:
        print("--- Group chat test ---")
        test_group_chat(master_token, group_chat_id, agent_tokens)

    if ok_count < total:
        print("\nSome tokens are missing. See setup instructions below.\n")
        _print_setup_instructions()

    print("\nDone.")


def _print_setup_instructions():
    print("HOW TO SET UP TELEGRAM BOTS:")
    print("=" * 50)
    print()
    print("Step 1: Create 4 bots via @BotFather")
    print("  - Open Telegram and search for @BotFather")
    print("  - Send /newbot for each bot you need:")
    print("    1. Master bot  (e.g. 'Squid Master Bot' / @squid_master_bot)")
    print("    2. Agent 1 bot (e.g. 'Squid Agent 1'    / @squid_agent1_bot)")
    print("    3. Agent 2 bot (e.g. 'Squid Agent 2'    / @squid_agent2_bot)")
    print("    4. Agent 3 bot (e.g. 'Squid Agent 3'    / @squid_agent3_bot)")
    print("  - BotFather gives you an HTTP API token for each (looks like")
    print("    '1234567890:ABCDefGhIjKlMnOpQrStUvWxYz')")
    print()
    print("Step 2: Create a Telegram group")
    print("  - Open Telegram, tap 'New Group'")
    print("  - Add all 4 bots as members (search by their @username)")
    print("  - Name it anything (the server renames it at game start)")
    print()
    print("Step 3: Make the master bot an admin")
    print("  - Open group settings → Administrators → Add Administrator")
    print("  - Select the master bot and grant it all permissions")
    print()
    print("Step 4: Get the group's chat_id")
    print("  - Send any message in the group")
    print("  - Open: https://api.telegram.org/bot<MASTER_TOKEN>/getUpdates")
    print("  - Look for 'chat': {'id': -100XXXXXXXXXX, ...}")
    print("  - That negative number is your TELEGRAM_GROUP_CHAT_ID")
    print()
    print("Step 5: Fill in your .env")
    print("  TELEGRAM_MASTER_BOT_TOKEN=<master bot token>")
    print("  TELEGRAM_GROUP_CHAT_ID=<chat id from step 4>")
    print("  AGENT_1_TELEGRAM_BOT_TOKEN=<agent 1 token>")
    print("  AGENT_2_TELEGRAM_BOT_TOKEN=<agent 2 token>")
    print("  AGENT_3_TELEGRAM_BOT_TOKEN=<agent 3 token>")
    print()
    print("Then re-run: python scripts/test_telegram.py")


if __name__ == "__main__":
    main()
