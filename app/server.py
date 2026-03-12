from uuid import uuid4
from fastapi import FastAPI
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from app.helpers import create_agent, send_usdc, get_usdc_balance, tick

app = FastAPI()
scheduler = BackgroundScheduler()
scheduler.start()

games: dict = {}

class AgentConfig(BaseModel):
    name: str
    model: str
    usdc_fee: float

class StartRequest(BaseModel):
    agents: list[AgentConfig]

@app.post("/start")
def start_game(req: StartRequest):
    raise NotImplementedError

@app.get("/state/{game_id}")
def get_state(game_id: str):
    raise NotImplementedError

@app.post("/stop/{game_id}")
def stop_game(game_id: str):
    raise NotImplementedError
