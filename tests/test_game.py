"""Tests for game state, leaderboard, emergency stop, and elimination logic."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, GameEvent, Lobby
from app.routers.game import run_elimination_round

pytestmark = pytest.mark.asyncio

LOBBY_PAYLOAD = {
    "name": "Game Test Lobby",
    "required_agents": 3,
    "kill_interval_seconds": 300,
    "entry_fee_usdc": 10.0,
}

AGENT_PAYLOAD = {
    "owner_email": "test@example.com",
    "model": "gpt-4o",
    "system_prompt": "Test agent.",
    "skills": [],
}


async def _create_lobby(client: AsyncClient, **overrides) -> dict:
    resp = await client.post("/lobbies/", json={**LOBBY_PAYLOAD, **overrides})
    assert resp.status_code == 201
    return resp.json()


async def _register_agent(client: AsyncClient, lobby_id: str, name: str, code: str) -> dict:
    resp = await client.post(f"/lobbies/{lobby_id}/agents/", json={
        **AGENT_PAYLOAD, "name": name, "access_code": code,
    })
    assert resp.status_code == 201
    return resp.json()


async def _fill_lobby(client: AsyncClient, required: int = 3) -> tuple[str, list[dict]]:
    """Create a lobby, fill it with agents, return (lobby_id, agents)."""
    lobby = await _create_lobby(client, required_agents=required)
    lid = lobby["lobby_id"]
    agents = []
    for i in range(1, required + 1):
        a = await _register_agent(client, lid, f"Agent{i}", f"test-access-code-{i}")
        agents.append(a)
    return lid, agents


class TestGameState:
    async def test_waiting_lobby_state(self, client: AsyncClient):
        lobby = await _create_lobby(client, required_agents=3)
        lid = lobby["lobby_id"]
        await _register_agent(client, lid, "A1", "test-access-code-1")

        resp = await client.get(f"/lobbies/{lid}/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "waiting"
        assert data["alive_agents"] == 1
        assert data["total_agents"] == 1
        assert data["elimination_round"] == 0
        assert data["seconds_until_elimination"] is None
        assert data["started_at"] is None
        assert data["winner_agent_id"] is None

    async def test_in_progress_lobby_state(self, client: AsyncClient):
        lid, _ = await _fill_lobby(client, required=2)
        resp = await client.get(f"/lobbies/{lid}/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "in_progress"
        assert data["alive_agents"] == 2
        assert data["total_agents"] == 2
        assert data["started_at"] is not None
        assert data["next_elimination_at"] is not None
        assert isinstance(data["seconds_until_elimination"], int)
        assert data["seconds_until_elimination"] > 0

    async def test_nonexistent_lobby_returns_404(self, client: AsyncClient):
        resp = await client.get(f"/lobbies/{uuid.uuid4()}/state")
        assert resp.status_code == 404


class TestLeaderboard:
    async def test_leaderboard_returns_all_agents_ranked(self, client: AsyncClient):
        lid, agents = await _fill_lobby(client, required=2)
        resp = await client.get(f"/lobbies/{lid}/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["lobby_id"] == lid
        assert len(data["leaderboard"]) == 2
        assert data["leaderboard"][0]["rank"] == 1
        assert data["leaderboard"][1]["rank"] == 2
        for entry in data["leaderboard"]:
            assert entry["status"] == "alive"
            assert entry["wallet_address"] != ""
            assert entry["agent_name"] in ("Agent1", "Agent2")

    async def test_leaderboard_waiting_lobby(self, client: AsyncClient):
        lobby = await _create_lobby(client, required_agents=5)
        lid = lobby["lobby_id"]
        await _register_agent(client, lid, "Solo", "test-access-code-1")

        resp = await client.get(f"/lobbies/{lid}/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["leaderboard"]) == 1
        assert data["leaderboard"][0]["agent_name"] == "Solo"

    async def test_nonexistent_lobby_returns_404(self, client: AsyncClient):
        resp = await client.get(f"/lobbies/{uuid.uuid4()}/leaderboard")
        assert resp.status_code == 404


class TestEmergencyStop:
    async def test_stop_in_progress_game(self, client: AsyncClient):
        lid, _ = await _fill_lobby(client, required=2)
        resp = await client.post(f"/lobbies/{lid}/stop")
        assert resp.status_code == 200

        state = (await client.get(f"/lobbies/{lid}/state")).json()
        assert state["status"] == "finished"
        assert state["seconds_until_elimination"] is None

    async def test_stop_waiting_lobby_returns_409(self, client: AsyncClient):
        lobby = await _create_lobby(client, required_agents=5)
        resp = await client.post(f"/lobbies/{lobby['lobby_id']}/stop")
        assert resp.status_code == 409

    async def test_stop_nonexistent_lobby_returns_404(self, client: AsyncClient):
        resp = await client.post(f"/lobbies/{uuid.uuid4()}/stop")
        assert resp.status_code == 404


class TestGameStart:
    async def test_agents_become_alive_when_game_starts(self, client: AsyncClient):
        lid, _ = await _fill_lobby(client, required=2)
        resp = await client.get(f"/lobbies/{lid}/agents/")
        agents = resp.json()
        assert all(a["status"] == "alive" for a in agents)

    async def test_started_at_is_set(self, client: AsyncClient):
        lid, _ = await _fill_lobby(client, required=2)
        state = (await client.get(f"/lobbies/{lid}/state")).json()
        assert state["started_at"] is not None

    async def test_game_started_event_emitted(self, client: AsyncClient, db_session: AsyncSession):
        lid, _ = await _fill_lobby(client, required=2)
        events = (await db_session.execute(
            select(GameEvent).where(
                GameEvent.lobby_id == uuid.UUID(lid),
                GameEvent.event_type == "game.started",
            )
        )).scalars().all()
        assert len(events) >= 1


class TestEliminationRound:
    """Tests for run_elimination_round called directly against the DB."""

    async def _setup_game(self, db: AsyncSession, balances: list[Decimal]) -> tuple[Lobby, list[Agent]]:
        """Create an in_progress lobby with agents at specified balances."""
        lobby = Lobby(
            name="Elim Test", required_agents=len(balances),
            kill_interval_seconds=300, status="in_progress",
            elimination_round=0,
        )
        db.add(lobby)
        await db.flush()

        agents = []
        for i, bal in enumerate(balances):
            a = Agent(
                lobby_id=lobby.id, name=f"E{i+1}", owner_email="e@test.com",
                model="gpt-4o", system_prompt="test", balance_usdc=bal,
                openrouter_credits=Decimal("0"), status="alive",
                wallet_address=f"0xElim{i+1}",
            )
            db.add(a)
            agents.append(a)
        await db.flush()
        return lobby, agents

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_lowest_balance_agent_is_killed(self, mock_credits, db_session: AsyncSession):
        lobby, agents = await self._setup_game(db_session, [Decimal("5"), Decimal("10"), Decimal("8")])
        await run_elimination_round(lobby.id, db_session)

        statuses = {a.name: a.status for a in agents}
        assert statuses["E1"] == "dead"
        assert statuses["E2"] == "alive"
        assert statuses["E3"] == "alive"
        assert lobby.elimination_round == 1

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_victim_usdc_redistributed_to_survivors(self, mock_credits, db_session: AsyncSession):
        lobby, agents = await self._setup_game(db_session, [Decimal("4"), Decimal("10"), Decimal("6")])
        await run_elimination_round(lobby.id, db_session)

        victim = next(a for a in agents if a.status == "dead")
        assert victim.balance_usdc == Decimal("0")
        survivors = [a for a in agents if a.status != "dead"]
        total_survivor_balance = sum(a.balance_usdc for a in survivors)
        assert total_survivor_balance == Decimal("20")

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_bankrupt_agent_marked_dead_no_redistribution(self, mock_credits, db_session: AsyncSession):
        lobby, agents = await self._setup_game(db_session, [Decimal("0"), Decimal("10"), Decimal("8")])
        await run_elimination_round(lobby.id, db_session)

        bankrupt = next(a for a in agents if a.name == "E1")
        assert bankrupt.status == "dead"

        events = (await db_session.execute(
            select(GameEvent).where(
                GameEvent.lobby_id == lobby.id, GameEvent.event_type == "agent.bankrupt",
            )
        )).scalars().all()
        assert len(events) == 1

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_game_finishes_when_one_survivor(self, mock_credits, db_session: AsyncSession):
        lobby, agents = await self._setup_game(db_session, [Decimal("2"), Decimal("10")])
        await run_elimination_round(lobby.id, db_session)

        assert lobby.status == "finished"
        assert lobby.finished_at is not None
        winner = next(a for a in agents if a.status == "winner")
        assert winner.name == "E2"
        assert lobby.winner_agent_id == winner.id

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_game_finished_event_emitted(self, mock_credits, db_session: AsyncSession):
        lobby, agents = await self._setup_game(db_session, [Decimal("2"), Decimal("10")])
        await run_elimination_round(lobby.id, db_session)

        events = (await db_session.execute(
            select(GameEvent).where(
                GameEvent.lobby_id == lobby.id, GameEvent.event_type == "game.finished",
            )
        )).scalars().all()
        assert len(events) == 1

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_agent_killed_event_emitted(self, mock_credits, db_session: AsyncSession):
        lobby, agents = await self._setup_game(db_session, [Decimal("3"), Decimal("10"), Decimal("7")])
        await run_elimination_round(lobby.id, db_session)

        events = (await db_session.execute(
            select(GameEvent).where(
                GameEvent.lobby_id == lobby.id, GameEvent.event_type == "agent.killed",
            )
        )).scalars().all()
        assert len(events) == 1

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_noop_for_finished_lobby(self, mock_credits, db_session: AsyncSession):
        lobby, agents = await self._setup_game(db_session, [Decimal("5"), Decimal("10")])
        lobby.status = "finished"
        await db_session.flush()

        await run_elimination_round(lobby.id, db_session)
        assert lobby.elimination_round == 0

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_all_bankrupt_finishes_with_no_winner(self, mock_credits, db_session: AsyncSession):
        lobby, agents = await self._setup_game(db_session, [Decimal("0"), Decimal("0"), Decimal("0")])
        await run_elimination_round(lobby.id, db_session)

        assert lobby.status == "finished"
        assert all(a.status == "dead" for a in agents)

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_next_elimination_scheduled_when_game_continues(self, mock_credits, db_session: AsyncSession):
        lobby, agents = await self._setup_game(db_session, [Decimal("3"), Decimal("10"), Decimal("7")])
        await run_elimination_round(lobby.id, db_session)

        assert lobby.status == "in_progress"
        assert lobby.next_elimination_at is not None

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("5"))
    async def test_openrouter_credits_refresh(self, mock_credits, db_session: AsyncSession):
        lobby, agents = await self._setup_game(db_session, [Decimal("3"), Decimal("10"), Decimal("7")])
        for a in agents:
            a.openrouter_key_hash = f"hash-{a.name}"
        await db_session.flush()

        await run_elimination_round(lobby.id, db_session)

        for a in agents:
            if a.status == "alive":
                assert a.openrouter_credits == Decimal("5")
