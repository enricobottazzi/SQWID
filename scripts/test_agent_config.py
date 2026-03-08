"""Smoke test: generate an agent config using real .env values.

No DB, no DO API calls — builds a config for Agent 1 using credentials
from .env, then prints the config and cloud-init script.
Writes config.json to /tmp for manual inspection.
"""

import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import dotenv_values

env = dotenv_values(Path(__file__).resolve().parent.parent / ".env")

from app.services.sandbox import build_agent_config, _cloud_init

fake_agent_1 = SimpleNamespace(
    id=uuid.uuid4(),
    name="TestBot Alpha",
    model="anthropic/claude-sonnet-4-6",
    system_prompt="You are an aggressive negotiator who never backs down.",
    skills=["# Skill 1: Balance Management\nMonitor your balance every 30 seconds."],
    openrouter_api_key="sk-or-v1-fake-subkey-for-testing",
    wallet_private_key=env.get("AGENT_1_WALLET_PRIVATE_KEY", ""),
    wallet_address=env.get("AGENT_1_WALLET_ADDRESS", "0xABC1"),
    telegram_bot_token=env.get("AGENT_1_TELEGRAM_BOT_TOKEN", ""),
    telegram_bot_user_id="111111111",
    agentmail_email_address="testbot-alpha@agentmail.to",
)

fake_agent_2 = SimpleNamespace(
    id=uuid.uuid4(),
    name="TestBot Beta",
    model="openai/gpt-4o",
    wallet_address=env.get("AGENT_2_WALLET_ADDRESS", "0xABC2"),
    telegram_bot_user_id="222222222",
)

fake_agent_3 = SimpleNamespace(
    id=uuid.uuid4(),
    name="TestBot Gamma",
    model="google/gemini-2.0-flash-001",
    wallet_address=env.get("AGENT_3_WALLET_ADDRESS", "0xABC3"),
    telegram_bot_user_id="333333333",
)

fake_lobby = SimpleNamespace(
    id=uuid.uuid4(),
    name="Demo Arena",
    required_agents=3,
    kill_interval_seconds=600,
    entry_fee_usdc=10.0,
)

all_agents = [fake_agent_1, fake_agent_2, fake_agent_3]
config = build_agent_config(fake_agent_1, fake_lobby, all_agents)

out_path = Path("/tmp/agent_config_test.json")
out_path.write_text(json.dumps(config, indent=2))
print(f"Config written to {out_path}\n")
print(json.dumps(config, indent=2))

print("\n--- cloud-init script ---\n")
print(_cloud_init(config))
