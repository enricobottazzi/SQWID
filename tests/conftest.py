"""Shared fixtures: in-memory SQLite async engine, session override, and test client."""

import asyncio
import json
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, event, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base

TEST_DATABASE_URL = "sqlite+aiosqlite://"


# Teach SQLite's DDL compiler how to render PostgreSQL-specific types.
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

_orig_jsonb = getattr(SQLiteTypeCompiler, "visit_JSONB", None)


def _visit_JSONB(self, type_, **kw):
    return "TEXT"


def _visit_UUID(self, type_, **kw):
    return "CHAR(32)"


SQLiteTypeCompiler.visit_JSONB = _visit_JSONB
if not hasattr(SQLiteTypeCompiler, "visit_UUID"):
    SQLiteTypeCompiler.visit_UUID = _visit_UUID


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)

    @event.listens_for(eng.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(engine) -> AsyncGenerator[AsyncClient, None]:
    from app.database import get_db
    from app.main import app

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    mock_key = AsyncMock(return_value={"key": "sk-or-test-key", "hash": "test-hash"})
    mock_discord_validate = AsyncMock(side_effect=lambda token: {
        "discord_token": token, "discord_user_id": f"discord-uid-{token[-1]}",
    })
    mock_discord_guild = AsyncMock(return_value={
        "guild_id": "test-guild-id",
        "channel_id": "test-channel-id",
        "invite_url": "https://discord.gg/test",
    })
    test_wallets = {
        f"test-access-code-{i}": {
            "wallet_address": f"0xTestWalletAddress{i}",
            "wallet_private_key": f"0xTestPrivateKey{i}",
            "discord_bot_token": f"test-discord-token-{i}",
        }
        for i in range(1, 4)
    }
    transport = ASGITransport(app=app)
    with (
        patch("app.services.openrouter.create_api_key", mock_key),
        patch("app.services.wallet._ACCESS_CODE_WALLETS", test_wallets),
        patch("app.services.discord.validate_bot_token", mock_discord_validate),
        patch("app.services.discord.setup_game_guild", mock_discord_guild),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    app.dependency_overrides.clear()
