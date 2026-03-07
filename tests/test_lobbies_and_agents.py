"""Tests for lobby and agent endpoints, including DB state verification."""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, Lobby

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LOBBY_PAYLOAD = {
    "name": "Test Lobby",
    "required_agents": 3,
    "kill_interval_seconds": 300,
    "entry_fee_usdc": 10.0,
}

AGENT_PAYLOAD = {
    "name": "Agent Alpha",
    "owner_email": "alpha@example.com",
    "model": "gpt-4o",
    "system_prompt": "You are agent alpha.",
    "skills": ["negotiation"],
    "access_code": "test-access-code-1",
}


async def _create_lobby(client: AsyncClient, **overrides) -> dict:
    payload = {**LOBBY_PAYLOAD, **overrides}
    resp = await client.post("/lobbies/", json=payload)
    assert resp.status_code == 201
    return resp.json()


async def _register_agent(client: AsyncClient, lobby_id: str, **overrides) -> dict:
    payload = {**AGENT_PAYLOAD, **overrides}
    resp = await client.post(f"/lobbies/{lobby_id}/agents/", json=payload)
    return resp.json(), resp.status_code


# ---------------------------------------------------------------------------
# Lobby CRUD
# ---------------------------------------------------------------------------


class TestCreateLobby:
    async def test_create_lobby_returns_201(self, client: AsyncClient):
        data = await _create_lobby(client)
        assert data["name"] == LOBBY_PAYLOAD["name"]
        assert data["required_agents"] == LOBBY_PAYLOAD["required_agents"]
        assert data["status"] == "waiting"
        assert data["game_wallet_address"] is None

    async def test_lobby_persists_in_db(self, client: AsyncClient, db_session: AsyncSession):
        data = await _create_lobby(client, name="Persist Check")
        lobby = await db_session.get(Lobby, uuid.UUID(data["lobby_id"]))
        assert lobby is not None
        assert lobby.name == "Persist Check"
        assert lobby.status == "waiting"


class TestListLobbies:
    async def test_list_returns_all(self, client: AsyncClient):
        await _create_lobby(client, name="L1")
        await _create_lobby(client, name="L2")
        resp = await client.get("/lobbies/")
        assert resp.status_code == 200
        names = {l["name"] for l in resp.json()}
        assert "L1" in names
        assert "L2" in names

    async def test_filter_by_status(self, client: AsyncClient):
        await _create_lobby(client, name="Waiting Lobby")
        resp = await client.get("/lobbies/", params={"status": "waiting"})
        assert resp.status_code == 200
        assert all(l["status"] == "waiting" for l in resp.json())

        resp2 = await client.get("/lobbies/", params={"status": "in_progress"})
        assert resp2.status_code == 200


class TestGetLobby:
    async def test_get_existing_lobby(self, client: AsyncClient):
        data = await _create_lobby(client, name="GetMe")
        resp = await client.get(f"/lobbies/{data['lobby_id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetMe"

    async def test_get_nonexistent_lobby_returns_404(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/lobbies/{fake_id}")
        assert resp.status_code == 404


class TestDeleteLobby:
    async def test_delete_waiting_lobby(self, client: AsyncClient, db_session: AsyncSession):
        data = await _create_lobby(client, name="ToDelete")
        lobby_id = data["lobby_id"]

        resp = await client.delete(f"/lobbies/{lobby_id}")
        assert resp.status_code == 204

        resp2 = await client.get(f"/lobbies/{lobby_id}")
        assert resp2.status_code == 404

    async def test_delete_nonexistent_lobby_returns_404(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.delete(f"/lobbies/{fake_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------


class TestRegisterAgent:
    async def test_register_agent_returns_201(self, client: AsyncClient):
        lobby = await _create_lobby(client, name="AgentLobby")
        agent_data, status = await _register_agent(client, lobby["lobby_id"])
        assert status == 201
        assert agent_data["name"] == AGENT_PAYLOAD["name"]
        assert agent_data["status"] == "registered"
        assert agent_data["lobby_id"] == lobby["lobby_id"]
        assert agent_data["agent_wallet_address"] is not None

    async def test_agent_persists_in_db(self, client: AsyncClient, db_session: AsyncSession):
        lobby = await _create_lobby(client, name="AgentDbLobby")
        agent_data, _ = await _register_agent(client, lobby["lobby_id"], name="DB Agent")
        agent = await db_session.get(Agent, uuid.UUID(agent_data["agent_id"]))
        assert agent is not None
        assert agent.name == "DB Agent"
        assert agent.lobby_id == uuid.UUID(lobby["lobby_id"])

    async def test_register_to_nonexistent_lobby_returns_404(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        _, status = await _register_agent(client, fake_id)
        assert status == 404

    async def test_lobby_full_returns_409(self, client: AsyncClient):
        lobby = await _create_lobby(client, name="SmallLobby", required_agents=2)
        lid = lobby["lobby_id"]
        _, s1 = await _register_agent(client, lid, name="A1", access_code="test-access-code-1")
        assert s1 == 201
        _, s2 = await _register_agent(client, lid, name="A2", access_code="test-access-code-2")
        assert s2 == 201
        _, s3 = await _register_agent(client, lid, name="A3", access_code="test-access-code-3")
        assert s3 == 409

    async def test_lobby_auto_starts_when_full(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        lobby = await _create_lobby(client, name="AutoStartLobby", required_agents=2)
        lid = lobby["lobby_id"]

        resp = await client.get(f"/lobbies/{lid}")
        assert resp.json()["status"] == "waiting"

        await _register_agent(client, lid, name="A1", access_code="test-access-code-1")
        await _register_agent(client, lid, name="A2", access_code="test-access-code-2")

        resp = await client.get(f"/lobbies/{lid}")
        assert resp.json()["status"] == "in_progress"

        db_lobby = await db_session.get(Lobby, uuid.UUID(lid))
        assert db_lobby is not None
        assert db_lobby.status == "in_progress"


class TestDeleteLobbyNotWaiting:
    async def test_cannot_delete_in_progress_lobby(self, client: AsyncClient):
        lobby = await _create_lobby(client, name="InProgressDelete", required_agents=1)
        lid = lobby["lobby_id"]
        await _register_agent(client, lid, name="FillIt", access_code="test-access-code-1")

        resp = await client.get(f"/lobbies/{lid}")
        assert resp.json()["status"] == "in_progress"

        resp = await client.delete(f"/lobbies/{lid}")
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Agent listing / retrieval
# ---------------------------------------------------------------------------


class TestListAgents:
    async def test_list_agents_in_lobby(self, client: AsyncClient):
        lobby = await _create_lobby(client, name="ListAgentsLobby", required_agents=5)
        lid = lobby["lobby_id"]
        await _register_agent(client, lid, name="X1", access_code="test-access-code-1")
        await _register_agent(client, lid, name="X2", access_code="test-access-code-2")

        resp = await client.get(f"/lobbies/{lid}/agents/")
        assert resp.status_code == 200
        agents = resp.json()
        assert len(agents) == 2
        assert {a["name"] for a in agents} == {"X1", "X2"}

    async def test_list_agents_nonexistent_lobby_returns_404(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/lobbies/{fake_id}/agents/")
        assert resp.status_code == 404


class TestGetAgent:
    async def test_get_agent_by_id(self, client: AsyncClient):
        lobby = await _create_lobby(client, name="GetAgentLobby", required_agents=5)
        lid = lobby["lobby_id"]
        agent_data, _ = await _register_agent(
            client, lid, name="FindMe", access_code="test-access-code-1"
        )

        resp = await client.get(f"/lobbies/{lid}/agents/{agent_data['agent_id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "FindMe"

    async def test_get_nonexistent_agent_returns_404(self, client: AsyncClient):
        lobby = await _create_lobby(client, name="NoAgentLobby", required_agents=5)
        fake_agent = str(uuid.uuid4())
        resp = await client.get(f"/lobbies/{lobby['lobby_id']}/agents/{fake_agent}")
        assert resp.status_code == 404

    async def test_get_agent_wrong_lobby_returns_404(self, client: AsyncClient):
        lobby1 = await _create_lobby(client, name="WrongLobby1", required_agents=5)
        lobby2 = await _create_lobby(client, name="WrongLobby2", required_agents=5)
        agent_data, _ = await _register_agent(
            client, lobby1["lobby_id"], name="CrossCheck", access_code="test-access-code-1"
        )
        resp = await client.get(f"/lobbies/{lobby2['lobby_id']}/agents/{agent_data['agent_id']}")
        assert resp.status_code == 404
