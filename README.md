# SQWID

## Start a server

Create a `.env` file at the project root with the following variables:

```env
JAKITUN_URL=              # Jakitun proxy server base URL
PRIVY_APP_ID=             # Privy application ID
PRIVY_APP_SECRET=         # Privy application secret
DAYTONA_API_KEY=          # Daytona API key
SERVER_PRIVATE_KEY=       # Private key of the server's treasury wallet (funds agents)
BASE_RPC_URL=             # Base mainnet RPC endpoint
```

Note that the server's treasury wallet must be funded with USDC on Base (to fund the agents) and with ETH (to pay for the gas).

Optionally, to enable [LangSmith](https://smith.langchain.com) tracing, add:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=          # LangSmith API key
LANGCHAIN_PROJECT=sqwid     # Project name in LangSmith
```

The server supports only one game at a time. Starting a new game while one is running returns a 400 error.

```bash
pip install -r requirements.txt
uvicorn app.server:app --reload --port 8001
```

## Run the test script

With the server running, in a separate terminal:

```bash
python test.py
```

This will start a game with two agents, poll the game state 3 times (10s apart), then stop the game. All output is logged to stdout.
