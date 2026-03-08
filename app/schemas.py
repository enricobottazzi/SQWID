"""Pydantic request/response schemas for the API."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# ── Lobby ──


class LobbyCreate(BaseModel):
    name: str
    required_agents: int
    kill_interval_seconds: int = 600
    entry_fee_usdc: float = 10.0


class LobbyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lobby_id: uuid.UUID
    name: str
    required_agents: int
    kill_interval_seconds: int
    entry_fee_usdc: Decimal
    status: str
    game_wallet_address: str | None
    created_at: datetime


# ── Agent ──


class AgentCreate(BaseModel):
    name: str
    owner_email: str
    model: str
    system_prompt: str
    skills: list[str] = []
    access_code: str


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_id: uuid.UUID
    lobby_id: uuid.UUID
    name: str
    owner_email: str
    agent_wallet_address: str | None
    agentmail_email_address: str | None
    model: str
    status: str
    created_at: datetime


# ── Game State ──


class GameStateResponse(BaseModel):
    lobby_id: uuid.UUID
    status: str
    started_at: datetime | None
    next_elimination_at: datetime | None
    seconds_until_elimination: int | None
    alive_agents: int
    total_agents: int
    elimination_round: int
    winner_agent_id: uuid.UUID | None


# ── Leaderboard ──


class LeaderboardEntry(BaseModel):
    rank: int
    agent_id: uuid.UUID
    agent_name: str
    wallet_address: str
    telegram_bot_username: str | None
    telegram_bot_user_id: str | None
    balance_usdc: Decimal
    status: str
    model: str
    killed_at_round: int | None


class LeaderboardResponse(BaseModel):
    lobby_id: uuid.UUID
    elimination_round: int
    next_elimination_at: datetime | None
    leaderboard: list[LeaderboardEntry]
