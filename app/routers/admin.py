"""Admin and observability endpoints."""

from uuid import UUID

from fastapi import APIRouter

router = APIRouter(prefix="/admin/lobbies/{lobby_id}", tags=["admin"])


@router.get("/events")
async def stream_events(lobby_id: UUID):
    """Server-Sent Events stream of all game events for a lobby.

    Event types:
    - game.started     — game has begun
    - agent.killed     — an agent was eliminated
    - agent.bankrupt   — an agent hit $0
    - game.finished    — a winner has been declared

    Returns an SSE stream. Clients should use EventSource or equivalent.
    """
    raise NotImplementedError