"""Lobby management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Lobby
from app.schemas import LobbyCreate, LobbyResponse

router = APIRouter(prefix="/lobbies", tags=["lobbies"])


def _lobby_to_response(lobby: Lobby) -> LobbyResponse:
    return LobbyResponse(
        lobby_id=lobby.id,
        name=lobby.name,
        required_agents=lobby.required_agents,
        kill_interval_seconds=lobby.kill_interval_seconds,
        entry_fee_usdc=lobby.entry_fee_usdc,
        status=lobby.status,
        game_wallet_address=lobby.game_wallet_address,
        created_at=lobby.created_at,
    )


@router.post("/", status_code=201, response_model=LobbyResponse)
async def create_lobby(body: LobbyCreate, db: AsyncSession = Depends(get_db)):
    lobby = Lobby(
        name=body.name,
        required_agents=body.required_agents,
        kill_interval_seconds=body.kill_interval_seconds,
        entry_fee_usdc=body.entry_fee_usdc,
        game_wallet_address=settings.game_wallet_address,
    )
    db.add(lobby)
    await db.commit()
    await db.refresh(lobby)
    return _lobby_to_response(lobby)


@router.get("/", response_model=list[LobbyResponse])
async def list_lobbies(status: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Lobby)
    if status is not None:
        stmt = stmt.where(Lobby.status == status)
    result = await db.execute(stmt)
    lobbies = result.scalars().all()
    return [_lobby_to_response(l) for l in lobbies]


@router.get("/{lobby_id}", response_model=LobbyResponse)
async def get_lobby(lobby_id: UUID, db: AsyncSession = Depends(get_db)):
    lobby = await db.get(Lobby, lobby_id)
    if lobby is None:
        raise HTTPException(status_code=404, detail="Lobby not found")
    return _lobby_to_response(lobby)


@router.delete("/{lobby_id}", status_code=204)
async def delete_lobby(lobby_id: UUID, db: AsyncSession = Depends(get_db)):
    lobby = await db.get(Lobby, lobby_id)
    if lobby is None:
        raise HTTPException(status_code=404, detail="Lobby not found")
    if lobby.status != "waiting":
        raise HTTPException(status_code=409, detail="Cannot delete a lobby that is not in 'waiting' status")
    await db.delete(lobby)
    await db.commit()
