from langchain_core.tools import tool
from langchain_privy import PrivyWalletTool
from pydantic import BaseModel, Field
from web3 import Web3

USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
TRANSFER_SIG = Web3.keccak(text="transfer(address,uint256)")[:4]


def init_send_usdc_tool(privy_tool: PrivyWalletTool):
    class SendUSDCInput(BaseModel):
        to: str = Field(description="Recipient wallet address")
        amount: float = Field(description="Amount of USDC to send (e.g. 0.5 for 0.5 USDC)")

    @tool("send_usdc", args_schema=SendUSDCInput)
    def send_usdc(to: str, amount: float) -> dict:
        """Send USDC (ERC-20) on Base to a recipient address."""
        raw_amount = int(amount * 1e6)
        to_padded = bytes.fromhex(Web3.to_checksum_address(to)[2:]).rjust(32, b"\x00")
        value_padded = raw_amount.to_bytes(32, "big")
        data = "0x" + (TRANSFER_SIG + to_padded + value_padded).hex()
        return privy_tool.invoke({
            "operation": "send_transaction",
            "chain": "base",
            "to": USDC_ADDRESS,
            "value": "0",
            "data": data,
        })

    return send_usdc
