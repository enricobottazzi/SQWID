from fastapi import FastAPI, HTTPException
from apscheduler.schedulers.background import BackgroundScheduler
from app.models import StartRequest
from app.helpers import create_agent, send_usdc, get_usdc_balance, tick

app = FastAPI()
scheduler = BackgroundScheduler()
scheduler.start()

current_game: dict | None = None

@app.post("/start")
def start_game(req: StartRequest):
    global current_game
    if current_game and current_game["status"] == "running":
        raise HTTPException(400, "A game is already running")
    raise NotImplementedError

@app.get("/state")
def get_state():
    if not current_game:
        raise HTTPException(404, "No game running")
    raise NotImplementedError

@app.post("/stop")
def stop_game():
    global current_game
    if not current_game or current_game["status"] != "running":
        raise HTTPException(404, "No game running")
    raise NotImplementedError
