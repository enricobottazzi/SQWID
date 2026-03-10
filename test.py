from dotenv import load_dotenv
from daytona import Daytona
from langchain_daytona import DaytonaSandbox
from langchain_privy import PrivyWalletTool
from deepagents import create_deep_agent

load_dotenv()

sandbox = Daytona().create()
backend = DaytonaSandbox(sandbox=sandbox)

privy_tool = PrivyWalletTool(chain_type="ethereum")
print(f"Wallet created! Address: {privy_tool.wallet_address}")

agent = create_deep_agent(
    backend=backend,
    tools=[privy_tool],
    system_prompt="You are a coding assistant with sandbox access and a crypto wallet on Base. You can create and run code in the sandbox, and perform wallet operations like checking your balance, signing messages, and sending transactions.",
)

try:
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "What is your wallet address on Base? Check your balance.",
                }
            ]
        }
    )
    print(result["messages"][-1].content)
finally:
    sandbox.stop()