"""Tests for the credit manager background task."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, Lobby
from app.services.credit_manager import _process_agent, run_credit_manager_cycle

pytestmark = pytest.mark.asyncio


async def _make_game(db: AsyncSession, agent_kwargs: list[dict]) -> tuple[Lobby, list[Agent]]:
    """Create an in-progress lobby with agents."""
    lobby = Lobby(
        name="Credit Test", required_agents=len(agent_kwargs),
        kill_interval_seconds=300, status="in_progress", elimination_round=0,
    )
    db.add(lobby)
    await db.flush()

    agents = []
    for i, kw in enumerate(agent_kwargs):
        defaults = dict(
            lobby_id=lobby.id, name=f"C{i+1}", owner_email="c@test.com",
            model="gpt-4o", system_prompt="test", status="alive",
            wallet_address=f"0xCredit{i+1}", openrouter_key_hash=f"hash-{i+1}",
            balance_usdc=Decimal("10"), openrouter_credits=Decimal("1"),
        )
        defaults.update(kw)
        a = Agent(**defaults)
        db.add(a)
        agents.append(a)
    await db.flush()
    return lobby, agents


class TestProcessAgent:
    """Unit tests for _process_agent — the per-agent credit check and top-up."""

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_no_topup_when_credits_above_threshold(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        _, agents = await _make_game(db_session, [{"openrouter_credits": Decimal("1")}])
        mock_balance.return_value = Decimal("2.00")

        await _process_agent(agents[0], db_session)

        mock_increase.assert_not_called()
        assert agents[0].openrouter_credits == Decimal("2.00")

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_standard_topup_when_wallet_has_enough(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        _, agents = await _make_game(db_session, [{
            "balance_usdc": Decimal("10"), "openrouter_credits": Decimal("0.30"),
        }])
        mock_balance.return_value = Decimal("0.30")

        await _process_agent(agents[0], db_session)

        mock_increase.assert_awaited_once_with("hash-1", Decimal("1.00"))
        assert agents[0].balance_usdc == Decimal("9.00")
        assert agents[0].openrouter_credits == Decimal("1.30")

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_partial_topup_when_wallet_has_less_than_standard(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        _, agents = await _make_game(db_session, [{
            "balance_usdc": Decimal("0.75"), "openrouter_credits": Decimal("0.20"),
        }])
        mock_balance.return_value = Decimal("0.20")

        await _process_agent(agents[0], db_session)

        mock_increase.assert_awaited_once_with("hash-1", Decimal("0.75"))
        assert agents[0].balance_usdc == Decimal("0")
        assert agents[0].openrouter_credits == Decimal("0.95")

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_no_topup_when_wallet_is_zero(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        _, agents = await _make_game(db_session, [{
            "balance_usdc": Decimal("0"), "openrouter_credits": Decimal("0.20"),
        }])
        mock_balance.return_value = Decimal("0.20")

        await _process_agent(agents[0], db_session)

        mock_increase.assert_not_called()
        assert agents[0].balance_usdc == Decimal("0")
        assert agents[0].openrouter_credits == Decimal("0.20")

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_brain_death_when_both_zero(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        _, agents = await _make_game(db_session, [{
            "balance_usdc": Decimal("0"), "openrouter_credits": Decimal("0"),
        }])
        mock_balance.return_value = Decimal("0")

        await _process_agent(agents[0], db_session)

        mock_increase.assert_not_called()
        assert agents[0].openrouter_credits == Decimal("0")
        assert agents[0].balance_usdc == Decimal("0")

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_skips_agent_without_key_hash(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        _, agents = await _make_game(db_session, [{"openrouter_key_hash": None}])

        await _process_agent(agents[0], db_session)

        mock_balance.assert_not_called()
        mock_increase.assert_not_called()

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_balance_fetch_failure_is_handled_gracefully(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        _, agents = await _make_game(db_session, [{"balance_usdc": Decimal("10")}])
        mock_balance.side_effect = Exception("network error")

        await _process_agent(agents[0], db_session)

        mock_increase.assert_not_called()

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_increase_limit_failure_does_not_sweep_usdc(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        _, agents = await _make_game(db_session, [{
            "balance_usdc": Decimal("10"), "openrouter_credits": Decimal("0.10"),
        }])
        mock_balance.return_value = Decimal("0.10")
        mock_increase.side_effect = Exception("API error")

        await _process_agent(agents[0], db_session)

        assert agents[0].balance_usdc == Decimal("10")
        assert agents[0].openrouter_credits == Decimal("0.10")

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_no_topup_at_exact_threshold(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        _, agents = await _make_game(db_session, [{
            "balance_usdc": Decimal("10"), "openrouter_credits": Decimal("0.50"),
        }])
        mock_balance.return_value = Decimal("0.50")

        await _process_agent(agents[0], db_session)

        mock_increase.assert_not_called()

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_credits_always_refreshed_from_openrouter(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        """Even when no top-up is needed, openrouter_credits should be updated."""
        _, agents = await _make_game(db_session, [{"openrouter_credits": Decimal("0.80")}])
        mock_balance.return_value = Decimal("3.50")

        await _process_agent(agents[0], db_session)

        assert agents[0].openrouter_credits == Decimal("3.50")

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_topup_when_credits_just_below_threshold(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        """$0.49 is below the $0.50 threshold — top-up should trigger."""
        _, agents = await _make_game(db_session, [{
            "balance_usdc": Decimal("10"), "openrouter_credits": Decimal("0.49"),
        }])
        mock_balance.return_value = Decimal("0.49")

        await _process_agent(agents[0], db_session)

        mock_increase.assert_awaited_once_with("hash-1", Decimal("1.00"))
        assert agents[0].balance_usdc == Decimal("9.00")
        assert agents[0].openrouter_credits == Decimal("1.49")

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_topup_when_wallet_has_exactly_one_dollar(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        """Wallet == $1.00 exactly: top-up should be $1.00 and wallet should hit $0."""
        _, agents = await _make_game(db_session, [{
            "balance_usdc": Decimal("1.00"), "openrouter_credits": Decimal("0.10"),
        }])
        mock_balance.return_value = Decimal("0.10")

        await _process_agent(agents[0], db_session)

        mock_increase.assert_awaited_once_with("hash-1", Decimal("1.00"))
        assert agents[0].balance_usdc == Decimal("0")
        assert agents[0].openrouter_credits == Decimal("1.10")

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_partial_topup_with_dust_wallet_balance(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        """Agent can squeeze every last cent — even $0.01 should be topped up."""
        _, agents = await _make_game(db_session, [{
            "balance_usdc": Decimal("0.01"), "openrouter_credits": Decimal("0.10"),
        }])
        mock_balance.return_value = Decimal("0.10")

        await _process_agent(agents[0], db_session)

        mock_increase.assert_awaited_once_with("hash-1", Decimal("0.01"))
        assert agents[0].balance_usdc == Decimal("0")
        assert agents[0].openrouter_credits == Decimal("0.11")

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_topup_with_drifted_credit_balance(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        """API-reported balance may differ from DB. Refresh happens before top-up math."""
        _, agents = await _make_game(db_session, [{
            "balance_usdc": Decimal("5.00"), "openrouter_credits": Decimal("0.80"),
        }])
        # Agent spent credits between cycles — API reports less than DB had.
        mock_balance.return_value = Decimal("0.10")

        await _process_agent(agents[0], db_session)

        mock_increase.assert_awaited_once_with("hash-1", Decimal("1.00"))
        # credits = API value (0.10) + top-up (1.00)
        assert agents[0].openrouter_credits == Decimal("1.10")
        assert agents[0].balance_usdc == Decimal("4.00")


class TestRunCreditManagerCycle:
    """Integration tests for the full credit manager cycle."""

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_processes_all_alive_agents_in_active_lobbies(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        mock_balance.return_value = Decimal("0.20")

        _, agents = await _make_game(db_session, [
            {"balance_usdc": Decimal("10")},
            {"balance_usdc": Decimal("8")},
        ])

        await run_credit_manager_cycle(db=db_session)

        assert mock_increase.await_count == 2

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_skips_dead_agents(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        mock_balance.return_value = Decimal("0.20")

        _, agents = await _make_game(db_session, [
            {"balance_usdc": Decimal("10"), "status": "alive", "openrouter_key_hash": "alive-dead-test-alive"},
            {"balance_usdc": Decimal("5"), "status": "dead", "openrouter_key_hash": "alive-dead-test-dead"},
        ])

        await run_credit_manager_cycle(db=db_session)

        called_hashes = [c.args[0] for c in mock_increase.call_args_list]
        assert "alive-dead-test-alive" in called_hashes
        assert "alive-dead-test-dead" not in called_hashes

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_skips_waiting_lobbies(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        mock_balance.return_value = Decimal("0.20")

        lobby = Lobby(
            name="Waiting", required_agents=3,
            kill_interval_seconds=300, status="waiting", elimination_round=0,
        )
        db_session.add(lobby)
        await db_session.flush()

        agent = Agent(
            lobby_id=lobby.id, name="W1", owner_email="w@test.com",
            model="gpt-4o", system_prompt="test", status="alive",
            wallet_address="0xW1", openrouter_key_hash="hash-w1",
            balance_usdc=Decimal("10"), openrouter_credits=Decimal("0.20"),
        )
        db_session.add(agent)
        await db_session.flush()

        await run_credit_manager_cycle(db=db_session)

        called_hashes = [c.args[0] for c in mock_balance.call_args_list]
        assert "hash-w1" not in called_hashes

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_skips_finished_lobbies(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        mock_balance.return_value = Decimal("0.20")

        lobby = Lobby(
            name="Finished", required_agents=2,
            kill_interval_seconds=300, status="finished", elimination_round=3,
        )
        db_session.add(lobby)
        await db_session.flush()

        agent = Agent(
            lobby_id=lobby.id, name="F1", owner_email="f@test.com",
            model="gpt-4o", system_prompt="test", status="alive",
            wallet_address="0xF1", openrouter_key_hash="hash-f1",
            balance_usdc=Decimal("10"), openrouter_credits=Decimal("0.20"),
        )
        db_session.add(agent)
        await db_session.flush()

        await run_credit_manager_cycle(db=db_session)

        called_hashes = [c.args[0] for c in mock_balance.call_args_list]
        assert "hash-f1" not in called_hashes

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_one_agent_failure_does_not_block_others(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        mock_balance.side_effect = [Exception("fail"), Decimal("0.20")]

        _, agents = await _make_game(db_session, [
            {"balance_usdc": Decimal("10")},
            {"balance_usdc": Decimal("8")},
        ])

        await run_credit_manager_cycle(db=db_session)

        assert mock_increase.await_count == 1

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_skips_winner_agents(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        mock_balance.return_value = Decimal("0.20")

        _, agents = await _make_game(db_session, [
            {"balance_usdc": Decimal("10"), "status": "alive", "openrouter_key_hash": "hash-alive-w"},
            {"balance_usdc": Decimal("5"), "status": "winner", "openrouter_key_hash": "hash-winner-w"},
        ])

        await run_credit_manager_cycle(db=db_session)

        called_hashes = [c.args[0] for c in mock_balance.call_args_list]
        assert "hash-alive-w" in called_hashes
        assert "hash-winner-w" not in called_hashes

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_skips_registered_agents(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        mock_balance.return_value = Decimal("0.20")

        _, agents = await _make_game(db_session, [
            {"balance_usdc": Decimal("10"), "status": "alive", "openrouter_key_hash": "hash-alive-r"},
            {"balance_usdc": Decimal("10"), "status": "registered", "openrouter_key_hash": "hash-registered-r"},
        ])

        await run_credit_manager_cycle(db=db_session)

        called_hashes = [c.args[0] for c in mock_balance.call_args_list]
        assert "hash-alive-r" in called_hashes
        assert "hash-registered-r" not in called_hashes

    @patch("app.services.credit_manager.openrouter.increase_spending_limit", new_callable=AsyncMock)
    @patch("app.services.credit_manager.openrouter.get_credit_balance", new_callable=AsyncMock)
    async def test_processes_agents_across_multiple_active_lobbies(
        self, mock_balance, mock_increase, db_session: AsyncSession,
    ):
        """Agents in different in_progress lobbies should all be processed."""
        mock_balance.return_value = Decimal("0.20")

        lobby_a = Lobby(
            name="Lobby A", required_agents=1,
            kill_interval_seconds=300, status="in_progress", elimination_round=0,
        )
        lobby_b = Lobby(
            name="Lobby B", required_agents=1,
            kill_interval_seconds=300, status="in_progress", elimination_round=0,
        )
        db_session.add_all([lobby_a, lobby_b])
        await db_session.flush()

        agent_a = Agent(
            lobby_id=lobby_a.id, name="A1", owner_email="a@test.com",
            model="gpt-4o", system_prompt="test", status="alive",
            wallet_address="0xA1", openrouter_key_hash="hash-lobby-a",
            balance_usdc=Decimal("10"), openrouter_credits=Decimal("0.20"),
        )
        agent_b = Agent(
            lobby_id=lobby_b.id, name="B1", owner_email="b@test.com",
            model="gpt-4o", system_prompt="test", status="alive",
            wallet_address="0xB1", openrouter_key_hash="hash-lobby-b",
            balance_usdc=Decimal("8"), openrouter_credits=Decimal("0.20"),
        )
        db_session.add_all([agent_a, agent_b])
        await db_session.flush()

        await run_credit_manager_cycle(db=db_session)

        called_hashes = [c.args[0] for c in mock_balance.call_args_list]
        assert "hash-lobby-a" in called_hashes
        assert "hash-lobby-b" in called_hashes
        increased_hashes = [c.args[0] for c in mock_increase.call_args_list]
        assert "hash-lobby-a" in increased_hashes
        assert "hash-lobby-b" in increased_hashes
