from fastapi import FastAPI

from app.routers import lobbies, agents, game, payments, admin

app = FastAPI(title="Squid Games OpenClaw", version="0.1.0")

app.include_router(lobbies.router)
app.include_router(agents.router)
app.include_router(game.router)
app.include_router(payments.router)
app.include_router(admin.router)
