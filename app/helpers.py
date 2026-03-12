def create_agent(config) -> dict:
    """Create Privy wallet, fund it, spin up Daytona sandbox, return agent handle."""
    raise NotImplementedError

def send_usdc(to_address: str, amount: float) -> str:
    """Transfer USDC from treasury wallet to target address. Returns tx hash."""
    raise NotImplementedError

def get_usdc_balance(wallet_address: str) -> float:
    """Read USDC balance on-chain for a given address."""
    raise NotImplementedError

def tick(game_id: str):
    """Scheduler callback: send a prompt to every agent in the game."""
    raise NotImplementedError
