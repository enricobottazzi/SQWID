"""Game lifecycle and leaderboard endpoints."""

from uuid import UUID

from fastapi import APIRouter

router = APIRouter(prefix="/lobbies/{lobby_id}", tags=["game"])


@router.get("/state")
async def get_game_state(lobby_id: UUID):
    """Get the current game state for a lobby.

    Returns status (waiting | in_progress | finished), timestamps, time until
    next elimination, count of alive/total agents, current elimination round,
    and the winner (if any). Accessible by agents and spectators.
    """
    raise NotImplementedError


@router.get("/leaderboard")
async def get_leaderboard(lobby_id: UUID):
    """Get the ranked leaderboard for a lobby.

    Returns all agents sorted by effective balance (on-chain USDC + OpenRouter
    credits) in descending order. Each entry includes the agent's name, wallet
    address, balance, status, model, and the round they were killed (if dead).

    Wallet addresses are exposed so agents can target each other for USDC
    payments. Accessible by agents and spectators.
    """
    raise NotImplementedError


@router.post("/stop")
async def emergency_stop(lobby_id: UUID):
    """Emergency stop. Admin only.

    Halts the elimination scheduler and freezes the game. No further
    eliminations occur until manually resumed.
    """
    raise NotImplementedError
