"""Agent registration and listing endpoints."""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Agent, GameEvent, Lobby
from app.schemas import AgentCreate, AgentResponse
from app.services import agentmail, openrouter, telegram, wallet

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lobbies/{lobby_id}/agents", tags=["agents"])


def _agent_to_response(agent: Agent) -> AgentResponse:
    return AgentResponse(
        agent_id=agent.id,
        lobby_id=agent.lobby_id,
        name=agent.name,
        owner_email=agent.owner_email,
        agent_wallet_address=agent.wallet_address,
        agentmail_email_address=agent.agentmail_email_address,
        model=agent.model,
        status=agent.status,
        created_at=agent.created_at,
    )


@router.post("/", status_code=201, response_model=AgentResponse)
async def register_agent(lobby_id: UUID, body: AgentCreate, db: AsyncSession = Depends(get_db)):
    lobby = await db.get(Lobby, lobby_id)
    if lobby is None:
        raise HTTPException(status_code=404, detail="Lobby not found")
    if lobby.status != "waiting":
        raise HTTPException(status_code=409, detail="Lobby is not accepting registrations")

    agent_count_result = await db.execute(
        select(func.count()).select_from(Agent).where(Agent.lobby_id == lobby_id)
    )
    agent_count = agent_count_result.scalar_one()
    if agent_count >= lobby.required_agents:
        raise HTTPException(status_code=409, detail="Lobby is already full")

    if not wallet.validate_access_code(body.access_code):
        raise HTTPException(status_code=403, detail="Invalid access code")

    wallet_info = wallet.get_wallet_by_access_code(body.access_code, lobby.entry_fee_usdc)
    openrouter_info = await openrouter.create_api_key(body.name)
    telegram_info = await telegram.validate_bot_token(wallet_info["telegram_bot_token"])
    agentmail_info = await agentmail.create_inbox(body.name)

    agent = Agent(
        lobby_id=lobby_id,
        name=body.name,
        owner_email=body.owner_email,
        model=body.model,
        system_prompt=body.system_prompt,
        skills=body.skills,
        wallet_address=wallet_info["wallet_address"],
        wallet_private_key=wallet_info["wallet_private_key"],
        balance_usdc=wallet_info["balance_usdc"],
        openrouter_api_key=openrouter_info["key"],
        openrouter_key_hash=openrouter_info["hash"],
        telegram_bot_token=telegram_info["telegram_bot_token"],
        telegram_bot_user_id=telegram_info["telegram_bot_user_id"],
        agentmail_inbox_id=agentmail_info["inbox_id"],
        agentmail_email_address=agentmail_info["email_address"],
        access_code=body.access_code,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    new_count = agent_count + 1
    if new_count >= lobby.required_agents:
        now = datetime.now(timezone.utc)
        lobby.status = "in_progress"
        lobby.started_at = now
        lobby.next_elimination_at = now + timedelta(seconds=lobby.kill_interval_seconds)
        all_agents = (await db.execute(
            select(Agent).where(Agent.lobby_id == lobby_id, Agent.status == "registered")
        )).scalars().all()
        for a in all_agents:
            a.status = "alive"
        await telegram.setup_game_group(
            lobby.name, [a.telegram_bot_token for a in all_agents if a.telegram_bot_token],
        )
        db.add(GameEvent(lobby_id=lobby_id, event_type="game.started",
                         payload={"started_at": now.isoformat()}))
        logger.info("[game.started] lobby=%s started_at=%s", lobby_id, now.isoformat())
        await db.commit()
        await db.refresh(agent)

    return _agent_to_response(agent)


@router.get("/", response_model=list[AgentResponse])
async def list_agents(lobby_id: UUID, db: AsyncSession = Depends(get_db)):
    lobby = await db.get(Lobby, lobby_id)
    if lobby is None:
        raise HTTPException(status_code=404, detail="Lobby not found")

    result = await db.execute(select(Agent).where(Agent.lobby_id == lobby_id))
    agents = result.scalars().all()
    return [_agent_to_response(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(lobby_id: UUID, agent_id: UUID, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.lobby_id != lobby_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_to_response(agent)
