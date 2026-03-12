from pydantic import BaseModel

class AgentConfig(BaseModel):
    name: str
    model: str
    usdc_fee: float

class StartRequest(BaseModel):
    agents: list[AgentConfig]
