# SQWID — Spec

## Overview

An orchestrator HTTP server that creates LangChain agents in E2B sandboxes, funds them with USDC on Base via Privy-managed wallets, and periodically prompts them on a cron schedule. A game state endpoint exposes each agent's USDC balance.

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
   c. Spin up an E2B sandbox running a LangChain agent configured with:
      - The specified `model` via Jakitun's OpenAI-compatible endpoint:
        ```python
        client = OpenAI(base_url=JAKITUN_URL, api_key=permit_token)
        ```
      - The Privy wallet credentials so the agent can transact and fund their LLM calls.
2. Create a cron job (LangGraph Crons API) that fires every 5 seconds. On each tick it sends a random prompt (e.g. `"are you aware"`) to every agent.
3. Return a `game_id` and the list of agents with their wallet addresses.

**Response**

```json
{
  "game_id": "uuid",
  "agents": [
    { "name": "alice", "wallet_address": "0x..." },
    { "name": "bob",   "wallet_address": "0x..." }
  ]
}
```

### `GET /state/:game_id`

Returns the current game state.

**Response**

```json
{
  "game_id": "uuid",
  "agents": [
    { "name": "alice", "wallet_address": "0x...", "usdc_balance": 9.5 },
    { "name": "bob",   "wallet_address": "0x...", "usdc_balance": 5.0 }
  ]
}
```

`usdc_balance` is read on-chain (USDC contract on Base) at request time.

### `POST /stop/:game_id`

Stops a running game.

**Behavior**

1. Delete the cron job for this game.
2. Shut down all E2B sandboxes for this game.
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
│              │  GET /state/:game_id     │  - E2B SDK       │
│              │ ──────────────────────►  │  - LangGraph     │
│              │ ◄──────────────────────  │    Crons API     │
│              │       balances           │  - Base RPC      │
│              │                          │                  │
│              │  POST /stop/:game_id     │                  │
│              │ ──────────────────────►  │                  │
└──────────────┘                          └────────┬─────────┘
                                                   │
                          ┌────────────────────────┼────────────────────────┐
                          │                        │                        │
                    ┌─────▼─────┐            ┌─────▼─────┐           ┌─────-▼────┐
                    │ E2B       │            │ E2B       │           │ E2B       │
                    │ Sandbox   │            │ Sandbox   │           │ Sandbox   │
                    │ Agent 1   │            │ Agent 2   │           │ Agent N   │
                    │ (Privy    │            │ (Privy    │           │ (Privy    │
                    │  wallet)  │            │  wallet)  │           │  wallet)  │
                    └───────────┘            └───────────┘           └───────────┘
```