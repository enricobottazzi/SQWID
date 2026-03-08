"""Game lifecycle, leaderboard endpoints, and elimination loop."""

import logging
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Agent, GameEvent, Lobby
from app.schemas import GameStateResponse, LeaderboardEntry, LeaderboardResponse
from app.config import settings
from app.services import openrouter, sandbox, usdc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lobbies/{lobby_id}", tags=["game"])


@router.get("/state", response_model=GameStateResponse)
async def get_game_state(lobby_id: UUID, db: AsyncSession = Depends(get_db)):
    lobby = await db.get(Lobby, lobby_id)
    if lobby is None:
        raise HTTPException(status_code=404, detail="Lobby not found")

    alive = (await db.execute(
        select(func.count()).select_from(Agent)
        .where(Agent.lobby_id == lobby_id, Agent.status.in_(["alive", "registered"]))
    )).scalar_one()
    total = (await db.execute(
        select(func.count()).select_from(Agent).where(Agent.lobby_id == lobby_id)
    )).scalar_one()

    seconds_until = None
    if lobby.next_elimination_at and lobby.status == "in_progress":
        nea = lobby.next_elimination_at
        now = datetime.now(timezone.utc)
        if nea.tzinfo is None:
            nea = nea.replace(tzinfo=timezone.utc)
        seconds_until = max(0, int((nea - now).total_seconds()))

    return GameStateResponse(
        lobby_id=lobby.id, status=lobby.status, started_at=lobby.started_at,
        next_elimination_at=lobby.next_elimination_at,
        seconds_until_elimination=seconds_until, alive_agents=alive,
        total_agents=total, elimination_round=lobby.elimination_round,
        winner_agent_id=lobby.winner_agent_id,
    )


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(lobby_id: UUID, db: AsyncSession = Depends(get_db)):
    lobby = await db.get(Lobby, lobby_id)
    if lobby is None:
        raise HTTPException(status_code=404, detail="Lobby not found")

    agents = list((await db.execute(
        select(Agent).where(Agent.lobby_id == lobby_id)
    )).scalars().all())
    agents.sort(key=lambda a: (a.status != "dead", a.effective_balance), reverse=True)

    return LeaderboardResponse(
        lobby_id=lobby.id, elimination_round=lobby.elimination_round,
        next_elimination_at=lobby.next_elimination_at,
        leaderboard=[
            LeaderboardEntry(
                rank=i + 1, agent_id=a.id, agent_name=a.name,
                wallet_address=a.wallet_address or "",
                telegram_bot_user_id=a.telegram_bot_user_id,
                balance_usdc=a.balance_usdc,
                status=a.status, model=a.model, killed_at_round=a.killed_at_round,
            )
            for i, a in enumerate(agents)
        ],
    )


# TODO: Add admin authentication before allowing this endpoint
@router.post("/stop")
async def emergency_stop(lobby_id: UUID, db: AsyncSession = Depends(get_db)):
    lobby = await db.get(Lobby, lobby_id)
    if lobby is None:
        raise HTTPException(status_code=404, detail="Lobby not found")
    if lobby.status != "in_progress":
        raise HTTPException(status_code=409, detail="Game is not in progress")

    lobby.status = "finished"
    lobby.finished_at = datetime.now(timezone.utc)
    lobby.next_elimination_at = None
    await db.commit()
    return {"detail": "Game stopped"}


async def run_elimination_round(lobby_id: UUID, db: AsyncSession):
    """Execute one elimination round for a lobby."""
    lobby = await db.get(Lobby, lobby_id)
    if lobby is None or lobby.status != "in_progress":
        return

    lobby.elimination_round += 1
    round_num = lobby.elimination_round

    alive = list((await db.execute(
        select(Agent).where(Agent.lobby_id == lobby_id, Agent.status == "alive")
    )).scalars().all())

    for a in alive:
        if a.wallet_address:
            try:
                a.balance_usdc = await usdc.get_usdc_balance(a.wallet_address)
            except Exception:
                logger.exception("Failed to read on-chain balance for agent %s", a.id)
        if a.openrouter_key_hash:
            try:
                a.openrouter_credits = await openrouter.get_credit_balance(a.openrouter_key_hash)
            except Exception:
                pass

    for a in alive:
        if a.effective_balance <= Decimal("0"):
            a.status = "dead"
            a.killed_at_round = round_num
            await _terminate_agent_sandbox(a)
            db.add(GameEvent(lobby_id=lobby.id, event_type="agent.bankrupt",
                             payload={"agent_id": str(a.id), "round": round_num}))
            logger.info("[agent.bankrupt] lobby=%s agent=%s round=%d", lobby.id, a.id, round_num)
    alive = [a for a in alive if a.status == "alive"]

    if len(alive) <= 1:
        await _finish_game(lobby, alive, db)
        await db.commit()
        return

    min_bal = min(a.effective_balance for a in alive)
    victim = random.choice([a for a in alive if a.effective_balance == min_bal])
    victim.status = "dead"
    victim.killed_at_round = round_num
    await _terminate_agent_sandbox(victim)

    survivors = [a for a in alive if a.id != victim.id]
    if survivors and victim.balance_usdc > Decimal("0"):
        share = victim.balance_usdc / len(survivors)
        for s in survivors:
            try:
                await usdc.transfer_usdc(settings.game_wallet_private_key, s.wallet_address, share)
            except Exception:
                logger.exception("Failed redistribution transfer to agent %s", s.id)
            s.balance_usdc += share
        victim.balance_usdc = Decimal("0")

    db.add(GameEvent(lobby_id=lobby.id, event_type="agent.killed",
                     payload={"agent_id": str(victim.id), "round": round_num}))
    logger.info("[agent.killed] lobby=%s agent=%s round=%d", lobby.id, victim.id, round_num)

    if len(survivors) <= 1:
        await _finish_game(lobby, survivors, db)
    else:
        lobby.next_elimination_at = datetime.now(timezone.utc) + timedelta(seconds=lobby.kill_interval_seconds)
    await db.commit()


async def _terminate_agent_sandbox(agent: Agent) -> None:
    if agent.droplet_id:
        try:
            await sandbox.terminate_sandbox(agent.droplet_id)
            agent.sandbox_status = "stopped"
        except Exception:
            logger.exception("Failed to terminate sandbox for agent=%s", agent.id)


async def _finish_game(lobby: Lobby, remaining: list[Agent], db: AsyncSession):
    lobby.status = "finished"
    lobby.finished_at = datetime.now(timezone.utc)
    lobby.next_elimination_at = None
    if remaining:
        remaining[0].status = "winner"
        lobby.winner_agent_id = remaining[0].id
        await _terminate_agent_sandbox(remaining[0])
    db.add(GameEvent(
        lobby_id=lobby.id, event_type="game.finished",
        payload={"winner_agent_id": str(remaining[0].id) if remaining else None},
    ))
    winner_id = remaining[0].id if remaining else None
    logger.info("[game.finished] lobby=%s winner=%s", lobby.id, winner_id)
