from uuid import uuid4
from fastapi import FastAPI, HTTPException
from apscheduler.schedulers.background import BackgroundScheduler
from app.models import StartRequest
from app.helpers import create_agent, get_usdc_balance, tick

app = FastAPI()
scheduler = BackgroundScheduler()
scheduler.start()

current_game: dict | None = None

@app.post("/start")
def start_game(req: StartRequest):
    global current_game
    if current_game and current_game["status"] == "running":
        raise HTTPException(400, "A game is already running")
    game_id = str(uuid4())
    agents = [create_agent(a) for a in req.agents]
    current_game = {"game_id": game_id, "agents": agents, "status": "running"}
    scheduler.add_job(tick, "interval", seconds=5, args=[current_game], id=game_id)
    return {"game_id": game_id, "agents": [{"name": a["name"], "wallet_address": a["wallet_address"]} for a in agents]}

@app.get("/state")
def get_state():
    if not current_game:
        raise HTTPException(404, "No game running")
    return {
        "game_id": current_game["game_id"],
        "agents": [
            {"name": a["name"], "wallet_address": a["wallet_address"], "usdc_balance": get_usdc_balance(a["wallet_address"])}
            for a in current_game["agents"]
        ],
    }

@app.post("/stop")
def stop_game():
    global current_game
    if not current_game or current_game["status"] != "running":
        raise HTTPException(404, "No game running")
    scheduler.remove_job(current_game["game_id"])
    for a in current_game["agents"]:
        a["sandbox"].stop()
    current_game["status"] = "stopped"
    return {"game_id": current_game["game_id"], "status": "stopped"}
