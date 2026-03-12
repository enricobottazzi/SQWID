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
from agentmail import AgentMail
from agentmail.inboxes.types import CreateInboxRequest
from app.models import AgentConfig
from tools.email import init_send_email_tool
from tools.usdc import init_send_usdc_tool

load_dotenv()

JAKITUN_URL = os.environ["JAKITUN_URL"]
SERVER_PRIVATE_KEY = os.environ["SERVER_PRIVATE_KEY"]
BASE_RPC_URL = os.environ["BASE_RPC_URL"]
AGENTMAIL_API_KEY = os.environ["AGENTMAIL_API_KEY"]

agentmail_client = AgentMail(api_key=AGENTMAIL_API_KEY)
USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
MAX_UINT256 = 2**256 - 1

w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
treasury_account = w3.eth.account.from_key(SERVER_PRIVATE_KEY)
SERVER_ADDRESS = treasury_account.address
USDC_ABI = json.loads('[{"inputs":[{"name":"owner","type":"address"}],"name":"nonces","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"name":"to","type":"address"},{"name":"value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"}]')
usdc_contract = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)


def _sign_permit(privy_tool: PrivyWalletTool) -> str:
    """Sign an EIP-2612 permit and return a base64-encoded token for Jakitun."""
    nonce = usdc_contract.functions.nonces(privy_tool.wallet_address).call()
    permit_domain = {
        "name": "USD Coin", "version": "2",
        "chainId": hex(8453), "verifyingContract": USDC_ADDRESS,
    }
    permit_types = {
        "Permit": [
            {"name": "owner", "type": "address"}, {"name": "spender", "type": "address"},
            {"name": "value", "type": "uint256"}, {"name": "nonce", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
        ],
        "EIP712Domain": [
            {"name": "name", "type": "string"}, {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"},
        ],
    }
    permit_message = {
        "owner": privy_tool.wallet_address, "spender": SERVER_ADDRESS,
        "value": hex(MAX_UINT256), "nonce": hex(nonce), "deadline": hex(MAX_UINT256),
    }
    wallet_info = list(privy_tool.wallets.values())[0]
    rpc_client = PrivyRPCClient(
        config=privy_tool.config,
        wallet_id=wallet_info["id"], wallet_address=wallet_info["address"],
    )
    sig_response = rpc_client.sign_typed_data(
        domain=permit_domain, types=permit_types, value=permit_message, chain="base",
    )
    signature = sig_response.get("data", {}).get("signature", sig_response.get("signature", ""))
    sig_bytes = bytes.fromhex(signature.removeprefix("0x"))
    return base64.b64encode(json.dumps({
        "owner": privy_tool.wallet_address, "spender": SERVER_ADDRESS,
        "value": str(MAX_UINT256), "deadline": MAX_UINT256,
        "v": sig_bytes[64], "r": "0x" + sig_bytes[:32].hex(), "s": "0x" + sig_bytes[32:64].hex(),
    }).encode()).decode()


def create_agent(config: AgentConfig) -> dict:
    """Create Privy wallet, fund it, spin up Daytona sandbox, return agent handle."""
    # 1a. Create Privy wallet
    privy_tool = PrivyWalletTool(chain_type="ethereum")

    # 1b. Fund wallet with USDC + gas ETH
    send_usdc(privy_tool.wallet_address, config.usdc_fee)
    send_eth(privy_tool.wallet_address, 0.000005)

    # 1c. Create AgentMail inbox
    inbox = agentmail_client.inboxes.create(request=CreateInboxRequest(username=f"{config.name}-{os.urandom(4).hex()}"))
    inbox_id = inbox.inbox_id
    email_tool = init_send_email_tool(inbox_id=inbox_id, api_key=AGENTMAIL_API_KEY)
    usdc_tool = init_send_usdc_tool(privy_tool)

    # 1d. Spin up Daytona sandbox + LangChain agent
    sandbox = daytona_client.create()
    permit_token = _sign_permit(privy_tool)
    model = ChatOpenAI(base_url=JAKITUN_URL, api_key=permit_token, model=config.model, max_tokens=4096)
    agent = create_deep_agent(
        model=model,
        backend=DaytonaSandbox(sandbox=sandbox),
        tools=[privy_tool, email_tool, usdc_tool],
        system_prompt="You are a coding assistant with sandbox access, a crypto wallet on Base, and an email inbox.",
    )
    return {
        "name": config.name,
        "wallet_address": privy_tool.wallet_address,
        "inbox_id": inbox_id,
        "agent": agent,
        "sandbox": sandbox,
    }


daytona_client = Daytona()


def cleanup_agent(agent: dict):
    """Permanently delete sandbox and email inbox for an agent."""
    daytona_client.delete(agent["sandbox"])
    agentmail_client.inboxes.delete(inbox_id=agent["inbox_id"])


def _send_tx(fn):
    tx = fn.build_transaction({"from": treasury_account.address, "nonce": w3.eth.get_transaction_count(treasury_account.address, "pending"), "gas": 200_000})
    signed = treasury_account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise Exception(f"Transaction reverted: {tx_hash.hex()}")
    return tx_hash.hex()

def send_eth(to_address: str, amount_eth: float) -> str:
    """Transfer ETH from server wallet to target address. Returns tx hash."""
    to = Web3.to_checksum_address(to_address)
    tx = {
        "from": treasury_account.address, "to": to,
        "value": w3.to_wei(amount_eth, "ether"),
        "nonce": w3.eth.get_transaction_count(treasury_account.address, "pending"),
        "gas": 21_000, "chainId": 8453,
        "maxFeePerGas": w3.eth.gas_price * 2,
        "maxPriorityFeePerGas": w3.to_wei(0.001, "gwei"),
    }
    signed = treasury_account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise Exception(f"ETH transfer reverted: {tx_hash.hex()}")
    return tx_hash.hex()

def send_usdc(to_address: str, amount: float) -> str:
    """Transfer USDC from server wallet to target address. Returns tx hash."""
    raw_amount = int(amount * 1e6)
    return _send_tx(usdc_contract.functions.transfer(Web3.to_checksum_address(to_address), raw_amount))


def get_usdc_balance(wallet_address: str) -> str:
    """Read USDC balance on-chain for a given address (6 decimal string)."""
    raw = usdc_contract.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
    return f"{raw / 1e6:.6f}"


TICK_PROMPTS = [
    "send 0.0001 USDC to 0x9992847Cb19492673457f7f088Eb2d102F98aeCC",
    # "send a random email to enricobottazzi@icloud.com",
]

def tick(game: dict):
    """Scheduler callback: send a prompt to every agent in the game."""
    import random
    prompt = random.choice(TICK_PROMPTS)
    for a in game["agents"]:
        result = a["agent"].invoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config={"metadata": {"game_id": game["game_id"], "agent_name": a["name"]}},
        )
        print(f"[{game['game_id']}] {a['name']}: {result['messages'][-1].content}")
