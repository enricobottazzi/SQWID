"""Agent registration and listing endpoints."""

from uuid import UUID

from fastapi import APIRouter

router = APIRouter(prefix="/lobbies/{lobby_id}/agents", tags=["agents"])


@router.post("/", status_code=201)
async def register_agent(lobby_id: UUID):
    """Register a new agent for a lobby.

    The user must have completed Stripe payment beforehand. Accepts agent name,
    owner email, OpenRouter model ID, system prompt, skills, and the Stripe
    checkout session ID.

    Server-side effects:
    - Verifies Stripe payment (stubbed: always succeeds)
    - Creates a crypto wallet for the agent (stubbed: in-DB balance)
    - Creates an OpenRouter API key (real integration)
    - Creates an AgentMail inbox (stubbed)
    - Registers the agent in the lobby

    If this registration fills the lobby to its required_agents count, the game
    starts automatically.

    Returns the created agent with wallet address and status "registered".
    """
    raise NotImplementedError


@router.get("/")
async def list_agents(lobby_id: UUID):
    """List all agents in a lobby.

    Returns an array of agent objects with names, statuses, and balances.
    """
    raise NotImplementedError


@router.get("/{agent_id}")
async def get_agent(lobby_id: UUID, agent_id: UUID):
    """Get details for a specific agent.

    Returns the full agent object including current balance and status.
    """
    raise NotImplementedError
