# SQWID

## Setup

Create a `.env` file at the project root with the following variables:

```env
JAKITUN_URL=              # Jakitun API base URL
PRIVY_APP_ID=             # Privy application ID
PRIVY_APP_SECRET=         # Privy application secret
DAYTONA_API_KEY=          # Daytona API key
TREASURY_PRIVATE_KEY=     # Private key of the server's treasury wallet (funds agents)
BASE_RPC_URL=             # Base mainnet RPC endpoint
```

Note that the server's treasury wallet must be funded with USDC on Base (to fund the agents) and with ETH (to pay for the gas).

The server supports only one game at a time. Starting a new game while one is running returns a 400 error.
