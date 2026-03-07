import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from sqlalchemy import select

from app.database import async_session
from app.models import Lobby
from app.routers import lobbies, agents, game, payments, admin

logger = logging.getLogger(__name__)


async def _poll_eliminations():
    while True:
        try:
            async with async_session() as db:
                due = (await db.execute(select(Lobby.id).where(
                    Lobby.status == "in_progress",
                    Lobby.next_elimination_at <= datetime.now(timezone.utc),
                ))).all()
                for (lobby_id,) in due:
                    await game.run_elimination_round(lobby_id, db)
        except Exception:
            logger.exception("Elimination poll error")
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_poll_eliminations())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Squid Games OpenClaw", version="0.1.0", lifespan=lifespan)

app.include_router(lobbies.router)
app.include_router(agents.router)
app.include_router(game.router)
app.include_router(payments.router)
app.include_router(admin.router)
