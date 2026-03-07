"""Tests for app.services.discord — bot validation and guild setup."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services import discord

pytestmark = pytest.mark.asyncio


def _mock_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=json_data, request=httpx.Request("GET", "https://x"))


class TestValidateBotToken:
    async def test_returns_token_and_user_id(self):
        resp = _mock_response({"id": "123456789", "username": "TestBot"})
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=resp):
            result = await discord.validate_bot_token("fake-token")
        assert result == {"discord_token": "fake-token", "discord_user_id": "123456789"}

    async def test_raises_on_invalid_token(self):
        resp = _mock_response({"message": "401: Unauthorized"}, 401)
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(httpx.HTTPStatusError):
                await discord.validate_bot_token("bad-token")


class TestSetupGameGuild:
    async def test_creates_guild_and_returns_info(self):
        guild_resp = _mock_response({"id": "g1"}, 200)
        channels_resp = _mock_response([{"id": "ch1", "type": 0, "name": "general"}], 200)
        patch_resp = _mock_response({"id": "ch1", "name": "town-square"}, 200)
        role_resp = _mock_response({"id": "r1", "name": "spectator"}, 200)
        invite_resp = _mock_response({"code": "abc123"}, 200)
        join_resp = _mock_response({}, 200)

        call_count = {"n": 0}
        post_responses = [guild_resp, role_resp, invite_resp, join_resp]
        get_responses = [channels_resp]

        async def fake_post(*args, **kwargs):
            idx = min(call_count["n"], len(post_responses) - 1)
            r = post_responses[idx]
            call_count["n"] += 1
            return r

        with (
            patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, side_effect=fake_post),
            patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=channels_resp),
            patch.object(httpx.AsyncClient, "patch", new_callable=AsyncMock, return_value=patch_resp),
            patch("app.services.discord.settings") as mock_settings,
        ):
            mock_settings.discord_master_bot_token = "master-token"
            result = await discord.setup_game_guild("TestLobby", ["token-1"])

        assert result["guild_id"] == "g1"
        assert result["channel_id"] == "ch1"
        assert "abc123" in result["invite_url"]
