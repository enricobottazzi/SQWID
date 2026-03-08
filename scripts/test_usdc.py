#!/usr/bin/env python3
"""Smoke-test on-chain USDC operations on Base mainnet.

Sends a tiny USDC payment (0.000001 = 1 raw unit) from Agent 2 to Agent 1 to
verify RPC connectivity, balance reads, signing, and transfer confirmation.

WARNING: This uses real USDC on Base mainnet.

Usage:
    source .venv/bin/activate
    python scripts/test_usdc.py
"""

import asyncio
import os
import sys
from decimal import Decimal

from dotenv import load_dotenv
from web3 import AsyncWeb3

load_dotenv()

BASE_RPC = os.environ.get("BASE_RPC_URL", "https://mainnet.base.org")
BASE_CHAIN_ID = 8453
USDC_ADDRESS = AsyncWeb3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
USDC_DECIMALS = 6
TRANSFER_AMOUNT = Decimal("0.000001")  # 1 raw unit — smallest possible

USDC_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
]


def _to_raw(amount: Decimal) -> int:
    return int(amount * (10 ** USDC_DECIMALS))


async def check_rpc() -> AsyncWeb3 | None:
    w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(BASE_RPC))
    try:
        chain_id = await w3.eth.chain_id
        print(f"  Connected — chain ID {chain_id}")
        if chain_id != BASE_CHAIN_ID:
            print(f"  WARNING — expected chain ID {BASE_CHAIN_ID}")
        return w3
    except Exception as exc:
        print(f"  FAILED — could not reach RPC: {exc}")
        return None


async def check_balance(w3: AsyncWeb3, label: str, address: str) -> Decimal | None:
    contract = w3.eth.contract(address=USDC_ADDRESS, abi=USDC_ABI)
    try:
        raw = await contract.functions.balanceOf(
            AsyncWeb3.to_checksum_address(address)
        ).call()
        balance = Decimal(raw) / (10 ** USDC_DECIMALS)
        print(f"  [{label}] {address}: {balance} USDC")
        return balance
    except Exception as exc:
        print(f"  [{label}] FAILED — could not read balance: {exc}")
        return None


async def transfer(w3: AsyncWeb3, private_key: str, to_address: str, amount: Decimal) -> str | None:
    account = w3.eth.account.from_key(private_key)
    contract = w3.eth.contract(address=USDC_ADDRESS, abi=USDC_ABI)
    try:
        tx = await contract.functions.transfer(
            AsyncWeb3.to_checksum_address(to_address),
            _to_raw(amount),
        ).build_transaction({
            "from": account.address,
            "nonce": await w3.eth.get_transaction_count(account.address),
            "chainId": BASE_CHAIN_ID,
        })
        signed = account.sign_transaction(tx)
        tx_hash = await w3.eth.send_raw_transaction(signed.raw_transaction)
        hex_hash = tx_hash.hex()
        print(f"  Tx sent: {hex_hash}")
        print(f"  Explorer: https://basescan.org/tx/{hex_hash}")
        return hex_hash
    except Exception as exc:
        print(f"  FAILED — transfer error: {exc}")
        return None


async def wait_for_receipt(w3: AsyncWeb3, tx_hash: str, timeout: int = 120) -> bool:
    try:
        receipt = await w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
        if receipt["status"] == 1:
            print(f"  Confirmed in block {receipt['blockNumber']} (status=1 OK)")
            return True
        print(f"  FAILED — tx reverted (status={receipt['status']})")
        return False
    except Exception as exc:
        print(f"  FAILED — could not get receipt: {exc}")
        return False


async def main():
    print("=== USDC Smoke Test (Base Mainnet) ===\n")
    print(f"Transfer amount: {TRANSFER_AMOUNT} USDC (1 raw unit)\n")

    sender_address = os.environ.get("AGENT_2_WALLET_ADDRESS", "")
    sender_key = os.environ.get("AGENT_2_WALLET_PRIVATE_KEY", "")
    receiver_address = os.environ.get("AGENT_1_WALLET_ADDRESS", "")

    missing = []
    if not sender_address or sender_address == "0x...":
        missing.append("AGENT_2_WALLET_ADDRESS")
    if not sender_key or sender_key == "0x...":
        missing.append("AGENT_2_WALLET_PRIVATE_KEY")
    if not receiver_address or receiver_address == "0x...":
        missing.append("AGENT_1_WALLET_ADDRESS")
    if missing:
        print(f"  SKIPPED — missing env vars: {', '.join(missing)}")
        print()
        _print_setup_instructions()
        sys.exit(1)

    ok = True

    # --- 1. RPC connectivity ---
    print("--- 1. RPC connectivity ---")
    w3 = await check_rpc()
    if not w3:
        sys.exit(1)

    # --- 2. Read balances (before) ---
    print("\n--- 2. Balances before transfer ---")
    sender_bal = await check_balance(w3, "Agent 2 (sender)", sender_address)
    receiver_bal = await check_balance(w3, "Agent 1 (receiver)", receiver_address)
    if sender_bal is None or receiver_bal is None:
        sys.exit(1)
    if sender_bal < TRANSFER_AMOUNT:
        print(f"  Agent 2 has insufficient USDC (need at least {TRANSFER_AMOUNT}).")
        sys.exit(1)

    # --- 3. Transfer USDC: Agent 2 → Agent 1 ---
    print(f"\n--- 3. Transfer {TRANSFER_AMOUNT} USDC: Agent 2 → Agent 1 ---")
    tx_hash = await transfer(w3, sender_key, receiver_address, TRANSFER_AMOUNT)
    if not tx_hash:
        ok = False
    else:
        print("  Waiting for confirmation...")
        if not await wait_for_receipt(w3, tx_hash):
            ok = False

    # --- 4. Verify balances after transfer ---
    if tx_hash and ok:
        print("\n--- 4. Balances after transfer ---")
        sender_after = await check_balance(w3, "Agent 2 (sender)", sender_address)
        receiver_after = await check_balance(w3, "Agent 1 (receiver)", receiver_address)

        if sender_after is not None and sender_after == sender_bal - TRANSFER_AMOUNT:
            print("  Sender balance decrease OK")
        elif sender_after is not None:
            print(f"  WARNING — expected sender balance {sender_bal - TRANSFER_AMOUNT}, got {sender_after}")

        if receiver_after is not None and receiver_after == receiver_bal + TRANSFER_AMOUNT:
            print("  Receiver balance increase OK")
        elif receiver_after is not None:
            print(f"  WARNING — expected receiver balance {receiver_bal + TRANSFER_AMOUNT}, got {receiver_after}")

    if ok:
        print("\nAll checks passed. USDC on-chain integration is working.")
    else:
        print("\nSome checks failed — see above.")
        sys.exit(1)


def _print_setup_instructions():
    print("HOW TO SET UP FOR USDC SMOKE TEST:")
    print("=" * 50)
    print()
    print("This test sends real USDC on Base mainnet (0.000001 USDC = 1 raw unit).")
    print()
    print("Required .env variables:")
    print("  AGENT_2_WALLET_ADDRESS=0x...")
    print("  AGENT_2_WALLET_PRIVATE_KEY=0x...")
    print("  AGENT_1_WALLET_ADDRESS=0x...")
    print()
    print("Agent 2 wallet needs:")
    print("  - A tiny amount of USDC (at least 0.000001)")
    print("  - Some ETH on Base for gas (~0.0001 ETH)")
    print()
    print("Then re-run: python scripts/test_usdc.py")


if __name__ == "__main__":
    asyncio.run(main())
