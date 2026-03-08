"""On-chain USDC operations on Base (L2)."""

from decimal import Decimal

from web3 import AsyncWeb3

from app.config import settings

USDC_ADDRESS = AsyncWeb3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
USDC_DECIMALS = 6
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


def _get_w3() -> AsyncWeb3:
    return AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(settings.base_rpc_url))


def _to_raw(amount: Decimal) -> int:
    return int(amount * (10 ** USDC_DECIMALS))


async def get_usdc_balance(wallet_address: str) -> Decimal:
    """Read on-chain USDC balance for *wallet_address*."""
    w3 = _get_w3()
    contract = w3.eth.contract(address=USDC_ADDRESS, abi=USDC_ABI)
    raw = await contract.functions.balanceOf(
        AsyncWeb3.to_checksum_address(wallet_address)
    ).call()
    return Decimal(raw) / (10 ** USDC_DECIMALS)


async def transfer_usdc(from_private_key: str, to_address: str, amount: Decimal) -> str:
    """Sign and broadcast a USDC transfer on Base. Returns tx hash hex."""
    w3 = _get_w3()
    account = w3.eth.account.from_key(from_private_key)
    contract = w3.eth.contract(address=USDC_ADDRESS, abi=USDC_ABI)

    tx = await contract.functions.transfer(
        AsyncWeb3.to_checksum_address(to_address),
        _to_raw(amount),
    ).build_transaction({
        "from": account.address,
        "nonce": await w3.eth.get_transaction_count(account.address, "pending"),
        "chainId": 8453,
    })

    signed = account.sign_transaction(tx)
    tx_hash = await w3.eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash.hex()
