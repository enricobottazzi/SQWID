import time
import signal
import sys
from dotenv import load_dotenv
from daytona import Daytona
from langchain_daytona import DaytonaSandbox
from langchain_privy import PrivyWalletTool
from deepagents import create_deep_agent

load_dotenv()

CRON_INTERVAL_SECONDS = 30
PROMPT = "What is your wallet address on Base? Check your balance."

sandbox = Daytona().create()
backend = DaytonaSandbox(sandbox=sandbox)

privy_tool = PrivyWalletTool(chain_type="ethereum")
print(f"Wallet created! Address: {privy_tool.wallet_address}")

agent = create_deep_agent(
    backend=backend,
    tools=[privy_tool],
    system_prompt="You are a coding assistant with sandbox access and a crypto wallet on Base. You can create and run code in the sandbox, and perform wallet operations like checking your balance, signing messages, and sending transactions.",
)

running = True

def shutdown(signum, frame):
    global running
    print("\nShutting down cron...")
    running = False

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

try:
    iteration = 0
    while running:
        iteration += 1
        print(f"\n{'='*60}")
        print(f"[Cron] Iteration {iteration} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        result = agent.invoke(
            {"messages": [{"role": "user", "content": PROMPT}]}
        )
        print(result["messages"][-1].content)

        if running:
            print(f"\n[Cron] Next run in {CRON_INTERVAL_SECONDS}s...")
            time.sleep(CRON_INTERVAL_SECONDS)
finally:
    print("\n[Cron] Cleaning up sandbox...")
    sandbox.stop()