"""Payment history endpoints (read-only)."""

from uuid import UUID

from fastapi import APIRouter

router = APIRouter(prefix="/lobbies/{lobby_id}/payments", tags=["payments"])


@router.get("/")
async def list_payments(lobby_id: UUID, agent_id: UUID | None = None):
    """List payment history for a lobby.

    Read-only view of all agent-to-agent USDC transfers derived from on-chain
    events (or the in-DB stub). Optionally filterable by agent_id.

    Returns an array of payment objects: from_wallet, to_wallet, amount,
    tx_hash, and timestamp.
    """
    raise NotImplementedError
