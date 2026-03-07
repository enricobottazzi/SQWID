"""Credit manager — background task that keeps agents' OpenRouter credits funded."""

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import Agent, Lobby
from app.services import openrouter

logger = logging.getLogger(__name__)


async def _process_agent(agent: Agent, db: AsyncSession) -> None:
    """Check one agent's credits and top up from wallet if needed."""
    if not agent.openrouter_key_hash:
        return

    try:
        credits = await openrouter.get_credit_balance(agent.openrouter_key_hash)
    except Exception:
        logger.exception("Failed to fetch credits for agent %s", agent.id)
        return

    agent.openrouter_credits = credits

    if credits >= settings.credit_threshold:
        return

    if agent.balance_usdc <= Decimal("0"):
        return

    top_up = min(settings.credit_topup_amount, agent.balance_usdc)

    try:
        await openrouter.increase_spending_limit(agent.openrouter_key_hash, top_up)
    except Exception:
        logger.exception("Failed to increase spending limit for agent %s", agent.id)
        return

    agent.balance_usdc -= top_up
    agent.openrouter_credits += top_up


async def run_credit_manager_cycle(db: AsyncSession) -> None:
    """Run one credit-manager pass over all alive agents in active lobbies."""
    rows = (await db.execute(
        select(Agent)
        .join(Lobby, Agent.lobby_id == Lobby.id)
        .where(Lobby.status == "in_progress", Agent.status == "alive")
    )).scalars().all()

    for agent in rows:
        await _process_agent(agent, db)

    await db.commit()
