"""SQLAlchemy ORM models mirroring schema.sql."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Lobby(Base):
    __tablename__ = "lobbies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    required_agents: Mapped[int] = mapped_column(Integer, nullable=False)
    kill_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=600)
    entry_fee_usdc: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False, default=Decimal("10.00"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="waiting")
    game_wallet_address: Mapped[str | None] = mapped_column(String(255))
    elimination_round: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_elimination_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    winner_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", use_alter=True, name="fk_lobbies_winner_agent_id"),
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    agents: Mapped[list["Agent"]] = relationship(
        back_populates="lobby", foreign_keys="Agent.lobby_id"
    )


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lobby_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lobbies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    wallet_address: Mapped[str | None] = mapped_column(String(255))
    wallet_seed_phrase: Mapped[str | None] = mapped_column(Text)
    wallet_private_key: Mapped[str | None] = mapped_column(String(255))
    openrouter_api_key: Mapped[str | None] = mapped_column(String(255))
    openrouter_key_hash: Mapped[str | None] = mapped_column(String(255))
    telegram_bot_token: Mapped[str | None] = mapped_column(String(255))
    telegram_bot_user_id: Mapped[str | None] = mapped_column(String(255))
    telegram_bot_username: Mapped[str | None] = mapped_column(String(255))
    agentmail_inbox_id: Mapped[str | None] = mapped_column(String(255))
    agentmail_email_address: Mapped[str | None] = mapped_column(String(255))
    balance_usdc: Mapped[Decimal] = mapped_column(DECIMAL(12, 6), nullable=False, default=Decimal("0"))
    openrouter_credits: Mapped[Decimal] = mapped_column(DECIMAL(12, 6), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="registered")
    killed_at_round: Mapped[int | None] = mapped_column(Integer)
    access_code: Mapped[str | None] = mapped_column(String(255))
    sandbox_status: Mapped[str | None] = mapped_column(String(20))
    droplet_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    lobby: Mapped["Lobby"] = relationship(back_populates="agents", foreign_keys=[lobby_id])

    @property
    def effective_balance(self) -> Decimal:
        return self.balance_usdc + self.openrouter_credits


class GameEvent(Base):
    __tablename__ = "game_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lobby_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lobbies.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
