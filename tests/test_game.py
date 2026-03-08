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

    @patch("app.routers.game.random.choice", side_effect=lambda xs: xs[0])
    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_tie_breaking_kills_exactly_one(self, mock_credits, mock_choice, db_session: AsyncSession):
        """When multiple agents share the lowest balance, exactly one is killed."""
        lobby, agents = await self._setup_game(db_session, [Decimal("5"), Decimal("5"), Decimal("10")])
        await run_elimination_round(lobby.id, db_session)

        dead = [a for a in agents if a.status == "dead"]
        alive = [a for a in agents if a.status == "alive"]
        assert len(dead) == 1
        assert len(alive) == 2
        assert dead[0].name in ("E1", "E2")

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_effective_balance_includes_openrouter_credits(self, mock_credits, db_session: AsyncSession):
        """Agent with low USDC but high credits survives over agent with higher USDC but no credits."""
        lobby, agents = await self._setup_game(db_session, [Decimal("3"), Decimal("7"), Decimal("20")])
        for a in agents:
            a.openrouter_key_hash = f"hash-{a.name}"
        await db_session.flush()

        async def _credits_by_hash(key_hash: str) -> Decimal:
            if key_hash == "hash-E1":
                return Decimal("5")  # E1: $3 USDC + $5 credits = $8 effective
            return Decimal("0")      # E2: $7+$0=$7, E3: $20+$0=$20
        mock_credits.side_effect = _credits_by_hash

        await run_elimination_round(lobby.id, db_session)

        assert agents[0].status == "alive"   # E1 ($8 effective) survives
        assert agents[1].status == "dead"    # E2 ($7 effective) is killed
        assert agents[2].status == "alive"   # E3 ($20 effective) survives

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_multiple_bankrupts_in_same_round(self, mock_credits, db_session: AsyncSession):
        """Multiple $0 agents are all marked dead, then lowest remaining is culled."""
        lobby, agents = await self._setup_game(
            db_session, [Decimal("0"), Decimal("0"), Decimal("5"), Decimal("10"), Decimal("15")]
        )
        await run_elimination_round(lobby.id, db_session)

        assert agents[0].status == "dead"   # bankrupt
        assert agents[1].status == "dead"   # bankrupt
        assert agents[2].status == "dead"   # culled (lowest remaining)
        assert agents[3].status == "alive"
        assert agents[4].status == "alive"

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_bankrupt_plus_cull_in_same_round(self, mock_credits, db_session: AsyncSession):
        """One agent bankrupt ($0) and the lowest remaining is also culled."""
        lobby, agents = await self._setup_game(
            db_session, [Decimal("0"), Decimal("3"), Decimal("10"), Decimal("7")]
        )
        await run_elimination_round(lobby.id, db_session)

        bankrupt = agents[0]
        assert bankrupt.status == "dead"

        culled = agents[1]  # E2 ($3) is the lowest remaining
        assert culled.status == "dead"

        assert agents[2].status == "alive"
        assert agents[3].status == "alive"

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_bankrupt_agent_no_redistribution_to_survivors(self, mock_credits, db_session: AsyncSession):
        """Bankrupt ($0) agent dying adds nothing to survivors' total."""
        lobby, agents = await self._setup_game(
            db_session, [Decimal("0"), Decimal("8"), Decimal("10"), Decimal("15")]
        )

        await run_elimination_round(lobby.id, db_session)

        assert agents[0].status == "dead"   # bankrupt — no redistribution
        assert agents[1].status == "dead"   # culled (lowest remaining)
        # Survivors get E2's $8 split: each gets $4
        survivors = [a for a in agents if a.status == "alive"]
        assert len(survivors) == 2
        total_survivor = sum(a.balance_usdc for a in survivors)
        # Original non-bankrupt total was $8+$10+$15=$33, nothing from E1's $0
        assert total_survivor == Decimal("33")

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_winner_balance_untouched(self, mock_credits, db_session: AsyncSession):
        """The winner's USDC stays in their wallet after the game finishes."""
        lobby, agents = await self._setup_game(db_session, [Decimal("2"), Decimal("15")])
        await run_elimination_round(lobby.id, db_session)

        winner = next(a for a in agents if a.status == "winner")
        assert winner.name == "E2"
        # Winner gets the victim's $2, so total = $15 + $2 = $17
        assert winner.balance_usdc == Decimal("17")

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_killed_at_round_set_correctly(self, mock_credits, db_session: AsyncSession):
        lobby, agents = await self._setup_game(db_session, [Decimal("3"), Decimal("10"), Decimal("7")])
        await run_elimination_round(lobby.id, db_session)

        victim = next(a for a in agents if a.status == "dead")
        assert victim.killed_at_round == 1
        assert lobby.elimination_round == 1

        for a in agents:
            if a.status == "alive":
                assert a.killed_at_round is None

    @patch("app.routers.game.openrouter.get_credit_balance", new_callable=AsyncMock, return_value=Decimal("0"))
    async def test_redistribution_with_odd_split(self, mock_credits, db_session: AsyncSession):
        """Redistributing among an uneven number of survivors preserves total USDC."""
        lobby, agents = await self._setup_game(
            db_session, [Decimal("6"), Decimal("10"), Decimal("8"), Decimal("12")]
        )
        total_before = sum(a.balance_usdc for a in agents)

        await run_elimination_round(lobby.id, db_session)

        victim = next(a for a in agents if a.status == "dead")
        assert victim.balance_usdc == Decimal("0")

        survivors = [a for a in agents if a.status != "dead"]
        total_after = sum(a.balance_usdc for a in survivors)
        assert total_after == total_before


class TestLeaderboardRanking:
    async def _setup_ranked_game(self, db: AsyncSession) -> tuple[Lobby, list[Agent]]:
        lobby = Lobby(
            name="Rank Test", required_agents=3,
            kill_interval_seconds=300, status="in_progress", elimination_round=0,
        )
        db.add(lobby)
        await db.flush()

        agents = []
        balances = [Decimal("5"), Decimal("15"), Decimal("10")]
        for i, bal in enumerate(balances):
            a = Agent(
                lobby_id=lobby.id, name=f"R{i+1}", owner_email="r@test.com",
                model="gpt-4o", system_prompt="test", balance_usdc=bal,
                openrouter_credits=Decimal("0"), status="alive",
                wallet_address=f"0xRank{i+1}",
            )
            db.add(a)
            agents.append(a)
        await db.flush()
        return lobby, agents

    async def test_leaderboard_ordered_by_effective_balance(self, client: AsyncClient, db_session: AsyncSession):
        lobby, agents = await self._setup_ranked_game(db_session)
        await db_session.commit()

        resp = await client.get(f"/lobbies/{lobby.id}/leaderboard")
        assert resp.status_code == 200
        lb = resp.json()["leaderboard"]

        assert lb[0]["agent_name"] == "R2"  # $15 — rank 1
        assert lb[0]["rank"] == 1
        assert lb[1]["agent_name"] == "R3"  # $10 — rank 2
        assert lb[1]["rank"] == 2
        assert lb[2]["agent_name"] == "R1"  # $5  — rank 3
        assert lb[2]["rank"] == 3

    async def test_leaderboard_includes_dead_agents(self, client: AsyncClient, db_session: AsyncSession):
        lobby, agents = await self._setup_ranked_game(db_session)
        agents[0].status = "dead"
        agents[0].killed_at_round = 1
        agents[0].balance_usdc = Decimal("0")
        await db_session.commit()

        resp = await client.get(f"/lobbies/{lobby.id}/leaderboard")
        assert resp.status_code == 200
        lb = resp.json()["leaderboard"]

        assert len(lb) == 3
        dead_entry = next(e for e in lb if e["agent_name"] == "R1")
        assert dead_entry["status"] == "dead"
        assert dead_entry["killed_at_round"] == 1


class TestEmergencyStopDetails:
    async def test_emergency_stop_sets_finished_at(self, client: AsyncClient, db_session: AsyncSession):
        lobby_data = (await client.post("/lobbies/", json={
            "name": "StopFinish", "required_agents": 2,
            "kill_interval_seconds": 300, "entry_fee_usdc": 10.0,
        })).json()
        lid = lobby_data["lobby_id"]
        await client.post(f"/lobbies/{lid}/agents/", json={
            "name": "S1", "owner_email": "s@test.com", "model": "gpt-4o",
            "system_prompt": "test", "skills": [], "access_code": "test-access-code-1",
        })
        await client.post(f"/lobbies/{lid}/agents/", json={
            "name": "S2", "owner_email": "s@test.com", "model": "gpt-4o",
            "system_prompt": "test", "skills": [], "access_code": "test-access-code-2",
        })

        resp = await client.post(f"/lobbies/{lid}/stop")
        assert resp.status_code == 200

        db_lobby = await db_session.get(Lobby, uuid.UUID(lid))
        assert db_lobby is not None
        assert db_lobby.finished_at is not None
        assert db_lobby.next_elimination_at is None
