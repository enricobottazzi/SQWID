"""Tests for app.services.telegram — bot validation and group chat setup."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services import telegram

pytestmark = pytest.mark.asyncio


def _mock_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=json_data, request=httpx.Request("GET", "https://x"))


class TestValidateBotToken:
    async def test_returns_token_and_user_id(self):
        resp = _mock_response({"ok": True, "result": {"id": 123456789, "is_bot": True, "first_name": "TestBot"}})
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=resp):
            result = await telegram.validate_bot_token("fake-token")
        assert result == {"telegram_bot_token": "fake-token", "telegram_bot_user_id": "123456789"}

    async def test_raises_on_invalid_token(self):
        resp = _mock_response({"ok": False, "description": "Unauthorized"}, 401)
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(httpx.HTTPStatusError):
                await telegram.validate_bot_token("bad-token")


class TestSetupGameGroup:
    async def test_sets_up_group_and_returns_info(self):
        ok_resp = _mock_response({"ok": True, "result": True})
        getme_resp = _mock_response({"ok": True, "result": {"id": 111}})
        invite_resp = _mock_response({"ok": True, "result": "https://t.me/+abc123"})

        post_calls = []

        async def fake_post(*args, **kwargs):
            post_calls.append(kwargs.get("json", {}))
            url = args[0] if args else kwargs.get("url", "")
            if "exportChatInviteLink" in str(url):
                return invite_resp
            return ok_resp

        with (
            patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, side_effect=fake_post),
            patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=getme_resp),
            patch("app.services.telegram.settings") as mock_settings,
        ):
            mock_settings.telegram_master_bot_token = "master-token"
            mock_settings.telegram_group_chat_id = "-100999"
            result = await telegram.setup_game_group("TestLobby", ["token-1"])

        assert result["group_chat_id"] == "-100999"
        assert "abc123" in result["invite_url"]

        # Verify the sequence: setChatTitle, setChatPermissions, promoteChatMember, exportChatInviteLink
        assert len(post_calls) == 4
        assert post_calls[0]["title"] == "TestLobby"
        assert post_calls[1]["permissions"]["can_send_messages"] is False
        assert post_calls[2]["user_id"] == 111
        assert post_calls[3]["chat_id"] == "-100999"
