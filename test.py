import time
import signal
import sys
import os
import json
import base64
from dotenv import load_dotenv
from daytona import Daytona
from langchain_daytona import DaytonaSandbox
from langchain_privy import PrivyWalletTool, PrivyRPCClient
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from web3 import Web3

load_dotenv()

CRON_INTERVAL_SECONDS = 30
PROMPT = "What is your wallet address on Base? Check your balance."

JAKITUN_URL = "https://30e6-193-221-143-82.ngrok-free.app"
SERVER_ADDRESS = "0x11c25ec12D3aBe509a37F23F950Aa6D0633Fce80"
BASE_RPC_URL = "https://mainnet.base.org"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # USDC on Base
MAX_UINT256 = 2**256 - 1

sandbox = Daytona().create()
backend = DaytonaSandbox(sandbox=sandbox)

privy_tool = PrivyWalletTool(chain_type="ethereum")
print(f"Wallet created! Address: {privy_tool.wallet_address}")

# --- Build Jakitun client with EIP-2612 permit signed by the agent wallet ---

w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
USDC_ABI = json.loads('[{"inputs":[{"name":"owner","type":"address"}],"name":"nonces","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]')
usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC), abi=USDC_ABI)
nonce = usdc.functions.nonces(privy_tool.wallet_address).call()

permit_types = {
    "Permit": [
        {"name": "owner", "type": "address"},
        {"name": "spender", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "nonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
    ],
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
}
permit_domain = {
    "name": "USD Coin",
    "version": "2",
    "chainId": hex(8453),
    "verifyingContract": USDC,
}
permit_message = {
    "owner": privy_tool.wallet_address,
    "spender": SERVER_ADDRESS,
    "value": hex(MAX_UINT256),
    "nonce": hex(nonce),
    "deadline": hex(MAX_UINT256),
}

wallet_info = list(privy_tool.wallets.values())[0]
rpc_client = PrivyRPCClient(
    config=privy_tool.config,
    wallet_id=wallet_info["id"],
    wallet_address=wallet_info["address"],
)

sig_response = rpc_client.sign_typed_data(
    domain=permit_domain,
    types=permit_types,
    value=permit_message,
    chain="base",
)
signature = sig_response.get("data", {}).get("signature", sig_response.get("signature", ""))

sig_bytes = bytes.fromhex(signature.removeprefix("0x"))
r = "0x" + sig_bytes[:32].hex()
s = "0x" + sig_bytes[32:64].hex()
v = sig_bytes[64]

permit_token = base64.b64encode(json.dumps({
    "owner": privy_tool.wallet_address,
    "spender": SERVER_ADDRESS,
    "value": str(MAX_UINT256),
    "deadline": MAX_UINT256,
    "v": v,
    "r": r,
    "s": s,
}).encode()).decode()

jakitun_model = ChatOpenAI(
    base_url=JAKITUN_URL,
    api_key=permit_token,
    model="openai/gpt-4o",
    max_tokens=4096,  # or whatever limit you want
)
print(f"Jakitun client created for wallet {privy_tool.wallet_address}")

# --- Create the agent ---

agent = create_deep_agent(
    model=jakitun_model,
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