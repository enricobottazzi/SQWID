"""Lobby management endpoints."""

from uuid import UUID

from fastapi import APIRouter

router = APIRouter(prefix="/lobbies", tags=["lobbies"])


@router.post("/", status_code=201)
async def create_lobby():
    """Create a new game lobby.

    Accepts a name, required agent count, kill interval, and entry fee.
    Returns the created lobby with a generated UUID and status "waiting".
    """
    raise NotImplementedError


@router.get("/")
async def list_lobbies(status: str | None = None):
    """List all lobbies, optionally filtered by status.

    Accepts an optional query param `status` (waiting | in_progress | finished).
    Returns an array of lobby objects.
    """
    raise NotImplementedError


@router.get("/{lobby_id}")
async def get_lobby(lobby_id: UUID):
    """Get details for a specific lobby.

    Returns the full lobby object including current status and configuration.
    """
    raise NotImplementedError


@router.delete("/{lobby_id}", status_code=204)
async def delete_lobby(lobby_id: UUID):
    """Cancel a lobby. Only allowed if status is "waiting".

    Returns 204 No Content on success. Fails if the lobby has already started.
    """
    raise NotImplementedError
