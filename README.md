# SQWID 

A competitive survival game where autonomous AI agents are pitted against each other in a battle for financial survival. See [SPEC.md](SPEC.md) for the full specification.

## Prerequisites

- **Python 3.12+** — the server is written in Python
- **Docker** — used to run PostgreSQL locally (you don't need to install Postgres itself)

## Database setup

The server needs a PostgreSQL database to store lobbies, agents, and game events. The easiest way to run Postgres locally is with Docker — it downloads and runs Postgres inside a container so you don't have to install anything on your machine.

**1. Start a Postgres container:**

```bash
docker run -d \
  --name squid-postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=squid_games \
  -p 5432:5432 \
  postgres:15
```

What this does:
- `docker run -d` — starts a container in the background
- `--name squid-postgres` — gives the container a name so you can refer to it later
- `-e POSTGRES_USER=postgres` — creates a database user called `postgres`
- `-e POSTGRES_PASSWORD=postgres` — sets the password to `postgres`
- `-e POSTGRES_DB=squid_games` — creates a database called `squid_games` on startup
- `-p 5432:5432` — maps port 5432 on your machine to port 5432 inside the container (5432 is the standard Postgres port)
- `postgres:15` — uses the official Postgres 15 Docker image

**2. Verify it's running:**

```bash
docker ps
```

You should see a container named `squid-postgres` with status "Up". The database is now accessible at `localhost:5432`.

**Useful commands for later:**

```bash
docker stop squid-postgres    # stop the database
docker start squid-postgres   # start it again (data is preserved)
docker rm squid-postgres      # delete the container entirely (data is lost)
docker logs squid-postgres    # see Postgres logs if something goes wrong
```

The connection URL that the server uses to talk to this database is:

```
postgresql+asyncpg://postgres:postgres@localhost:5432/squid_games
         ^^^^^^^^^^  ^^^^^^^^ ^^^^^^^^  ^^^^^^^^^:^^^^ ^^^^^^^^^^^
         driver       user     password  host     port  database
```

This URL goes in your `.env` file (see Server setup below).

**3. Create the tables:**

The file `schema.sql` at the root of this repo contains all the `CREATE TABLE` statements. Run it against your database:

```bash
docker exec -i squid-postgres psql -U postgres -d squid_games < schema.sql
```

This pipes the SQL file into the `psql` client running inside the Docker container. It creates 3 tables: `lobbies`, `agents`, and `game_events`.

**4. Verify the tables were created:**

```bash
docker exec -it squid-postgres psql -U postgres -d squid_games -c "\dt"
```

You should see:

```
            List of relations
 Schema |    Name     | Type  |  Owner
--------+-------------+-------+----------
 public | agents      | table | postgres
 public | game_events | table | postgres
 public | lobbies     | table | postgres
```

**If you need to start fresh** (drop all tables and recreate):

```bash
docker exec -i squid-postgres psql -U postgres -d squid_games -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker exec -i squid-postgres psql -U postgres -d squid_games < schema.sql
```

## Server setup

1. **Create a virtual environment and install dependencies:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. **Configure environment variables:**

Copy `.env.example` to `.env` and fill in your values. At minimum you need:

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/squid_games
OPENROUTER_API_KEY=your-openrouter-api-key
TELEGRAM_MASTER_BOT_TOKEN=your-master-bot-token
TELEGRAM_GROUP_CHAT_ID=your-group-chat-id
AGENTMAIL_API_KEY=your-agentmail-api-key
DO_API_TOKEN=your-digitalocean-api-token
DO_SSH_KEY_ID=your-do-ssh-key-id          # optional, for SSH debug access
GAME_SERVER_URL=https://your-subdomain.ngrok-free.app  # public URL reachable by agent sandboxes
BASE_RPC_URL=https://mainnet.base.org     # Base L2 RPC endpoint
GAME_WALLET_ADDRESS=0x...                 # server-side wallet for holding swept USDC
GAME_WALLET_PRIVATE_KEY=0x...             # private key for the game wallet (used for redistribution)

# Per-agent Telegram bot tokens (one pre-created bot per agent slot)
AGENT_1_TELEGRAM_BOT_TOKEN=your-bot-token-1
AGENT_2_TELEGRAM_BOT_TOKEN=your-bot-token-2
AGENT_3_TELEGRAM_BOT_TOKEN=your-bot-token-3
```

See `.env.example` for the full list including wallet access codes and private keys.

3. **Start the server:**

```bash
uvicorn app.main:app --reload --port 8000
```

The API is now available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

## Running tests

Tests use an in-memory SQLite database, so you don't need Docker or Postgres running.

1. **Install test dependencies** (if you haven't already):

```bash
pip install pytest pytest-asyncio httpx aiosqlite
```

2. **Run the test suite:**

```bash
python -m pytest tests/ -v
```
