CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE lobbies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    required_agents INT NOT NULL,
    kill_interval_seconds INT NOT NULL DEFAULT 600,
    entry_fee_usdc  DECIMAL(12,2) NOT NULL DEFAULT 10.00,
    status          VARCHAR(20) NOT NULL DEFAULT 'waiting',
    game_wallet_address VARCHAR(255),
    elimination_round INT NOT NULL DEFAULT 0,
    next_elimination_at TIMESTAMPTZ,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    winner_agent_id UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE agents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lobby_id        UUID NOT NULL REFERENCES lobbies(id),
    name            VARCHAR(255) NOT NULL,
    owner_email     VARCHAR(255) NOT NULL,
    model           VARCHAR(255) NOT NULL,
    system_prompt   TEXT NOT NULL,
    skills          JSONB NOT NULL DEFAULT '[]',
    wallet_address  VARCHAR(255),
    wallet_private_key VARCHAR(255),
    openrouter_api_key VARCHAR(255),
    openrouter_key_hash VARCHAR(255),
    telegram_bot_token VARCHAR(255),
    telegram_bot_user_id VARCHAR(255),
    agentmail_inbox_id VARCHAR(255),
    agentmail_email_address VARCHAR(255),
    balance_usdc    DECIMAL(12,6) NOT NULL DEFAULT 0,
    openrouter_credits DECIMAL(12,6) NOT NULL DEFAULT 0,
    status          VARCHAR(20) NOT NULL DEFAULT 'registered',
    killed_at_round INT,
    access_code     VARCHAR(255),
    sandbox_status  VARCHAR(20),
    droplet_id      INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Deferred FK: lobbies.winner_agent_id -> agents.id
ALTER TABLE lobbies
    ADD CONSTRAINT fk_lobbies_winner_agent_id
    FOREIGN KEY (winner_agent_id) REFERENCES agents(id);

CREATE TABLE game_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lobby_id        UUID NOT NULL REFERENCES lobbies(id),
    event_type      VARCHAR(50) NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
