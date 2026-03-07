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
    model: str
    status: str
    created_at: datetime
