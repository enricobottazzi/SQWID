"""
Integration test script for the SQWID server.
Assumes the server is already running at BASE_URL.

Flow: POST /start → poll GET /state → POST /stop
"""

import time
import requests
import json

BASE_URL = "http://localhost:8001"

def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def pp(data: dict):
    print(json.dumps(data, indent=2))

# --- 1. Start a game ---
log("Starting game...")
start_payload = {
    "agents": [
        {"name": "alice", "model": "openai/gpt-4o", "usdc_fee": 0.1},
        {"name": "bob", "model": "openai/gpt-4o-mini", "usdc_fee": 0.1},
    ]
}
r = requests.post(f"{BASE_URL}/start", json=start_payload)
r.raise_for_status()
start_data = r.json()
log("Game started:")
pp(start_data)

game_id = start_data["game_id"]

# --- 2. Poll state a few times ---
POLL_ROUNDS = 3
POLL_INTERVAL = 10

for i in range(1, POLL_ROUNDS + 1):
    log(f"Polling state ({i}/{POLL_ROUNDS})...")
    r = requests.get(f"{BASE_URL}/state")
    r.raise_for_status()
    state = r.json()
    pp(state)
    if i < POLL_ROUNDS:
        time.sleep(POLL_INTERVAL)

# --- 3. Stop the game ---
log("Stopping game...")
r = requests.post(f"{BASE_URL}/stop")
r.raise_for_status()
stop_data = r.json()
log("Game stopped:")
pp(stop_data)

log("Done.")
