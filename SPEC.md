# SQWID — Spec

## Overview

An orchestrator HTTP server that creates LangChain agents in Daytona sandboxes, funds them with USDC on Base via Privy-managed wallets, and periodically prompts them on a cron schedule. A game state endpoint exposes each agent's USDC balance.

## API

### `POST /start`

Starts a new game.

**Request body**

```json
{
  "agents": [
    { "name": "alice", "model": "gpt-4o", "usdc_fee": 10.0 },
    { "name": "bob",   "model": "gpt-4o-mini", "usdc_fee": 5.0 }
  ]
}
```

**Behavior**

1. For each agent entry:
   a. Create a Privy embedded wallet → obtain its Base address.
   b. Fund the wallet with `usdc_fee` USDC on Base (server's treasury wallet sends the transfer).
   c. Create an AgentMail inbox for the agent → obtain its inbox address (e.g. `alice@agentmail.to`).
   d. Spin up a Daytona sandbox running a LangChain agent configured with:
      - The specified `model` via Jakitun's OpenAI-compatible endpoint:
        ```python
        client = OpenAI(base_url=JAKITUN_URL, api_key=permit_token)
        ```
      - The Privy wallet credentials so the agent can transact on Base and fund their LLM calls (via Jakitun proxy server).
      - The AgentMail inbox address so the agent can send and receive emails.
2. Schedule an in-process job (APScheduler) that fires every N seconds. On each tick it sends a prompt to every agent.
3. Return a `game_id` and the list of agents with their wallet addresses.

**Response**

```json
{
  "game_id": "uuid",
  "agents": [
    { "name": "alice", "wallet_address": "0x...", "inbox": "alice-<game_id>@agentmail.to" },
    { "name": "bob",   "wallet_address": "0x...", "inbox": "bob-<game_id>@agentmail.to" }
  ]
}
```

### `GET /state`

Returns the current game state.

**Response**

```json
{
  "game_id": "uuid",
  "agents": [
    { "name": "alice", "wallet_address": "0x...", "usdc_balance": 9.5, "inbox": "alice-<game_id>@agentmail.to" },
    { "name": "bob",   "wallet_address": "0x...", "usdc_balance": 5.0, "inbox": "bob-<game_id>@agentmail.to" }
  ]
}
```

`usdc_balance` is read on-chain (USDC contract on Base) at request time.

### `POST /stop`

Stops a running game.

**Behavior**

1. Remove the APScheduler job for this game.
2. Shut down all Daytona sandboxes for this game.
3. Mark the game as stopped.

**Response**

```json
{ "game_id": "uuid", "status": "stopped" }
```

## Architecture

```
┌──────────────┐       POST /start        ┌──────────────────┐
│   Client     │ ──────────────────────►  │  Orchestrator    │
│              │ ◄──────────────────────  │  Server          │
│              │       game_id + addrs    │                  │
│              │                          │  - Privy SDK     │
│              │  GET /state              │  - Daytona SDK   │
│              │ ──────────────────────►  │  - AgentMail SDK │
│              │ ◄──────────────────────  │  - APScheduler   │
│              │       balances           │  - Base RPC      │
│              │                          │                  │
│              │  POST /stop              │                  │
│              │ ──────────────────────►  │                  │
└──────────────┘                          └────────┬─────────┘
                                                   │
                          ┌────────────────────────┼────────────────────────┐
                          │                        │                        │
                    ┌─────▼─────┐            ┌─────▼─────┐           ┌─────-▼────┐
                    │ Daytona   │            │ Daytona   │           │ Daytona   │
                    │ Sandbox   │            │ Sandbox   │           │ Sandbox   │
                    │ Agent 1   │            │ Agent 2   │           │ Agent N   │
                    │ (Privy    │            │ (Privy    │           │ (Privy    │
                    │  wallet + │            │  wallet + │           │  wallet + │
                    │  inbox)   │            │  inbox)   │           │  inbox)   │
                    └───────────┘            └───────────┘           └───────────┘
```