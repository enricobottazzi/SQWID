"""Tests for app.services.openrouter — key provisioning and credit balance."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services import openrouter

pytestmark = pytest.mark.asyncio


def _mock_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=json_data, request=httpx.Request("GET", "https://x"))


class TestCreateApiKey:
    async def test_returns_key_and_hash(self):
        resp = _mock_response(
            {"key": "sk-or-abc123", "data": {"hash": "h_abc123"}}, 201
        )
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=resp):
            result = await openrouter.create_api_key("TestAgent")
        assert result == {"key": "sk-or-abc123", "hash": "h_abc123"}

    async def test_raises_on_http_error(self):
        resp = _mock_response({"error": {"message": "unauthorized"}}, 401)
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(httpx.HTTPStatusError):
                await openrouter.create_api_key("FailAgent")


class TestGetCreditBalance:
    async def test_returns_remaining_credits(self):
        resp = _mock_response({"data": {"limit_remaining": 3.45}})
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=resp):
            balance = await openrouter.get_credit_balance("h_abc123")
        assert balance == Decimal("3.45")

    async def test_returns_zero_when_limit_is_null(self):
        resp = _mock_response({"data": {"limit_remaining": None}})
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=resp):
            balance = await openrouter.get_credit_balance("h_abc123")
        assert balance == Decimal("0")

    async def test_raises_on_http_error(self):
        resp = _mock_response({"error": {"message": "forbidden"}}, 403)
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(httpx.HTTPStatusError):
                await openrouter.get_credit_balance("bad_hash")
