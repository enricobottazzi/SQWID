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

fake_agent = SimpleNamespace(
    id=uuid.uuid4(),
    name="TestBot Alpha",
    model="anthropic/claude-sonnet-4-6",
    system_prompt="You are an aggressive negotiator who never backs down.",
    skills=["# Skill 1: Balance Management\nMonitor your balance every 30 seconds."],
    openrouter_api_key=env.get("OPENROUTER_PROVISIONING_KEY", ""),
    wallet_private_key=env.get("AGENT_1_WALLET_PRIVATE_KEY", ""),
    telegram_bot_token=env.get("AGENT_1_TELEGRAM_BOT_TOKEN", ""),
    agentmail_email_address="testbot@agentmail.to",
)

fake_lobby = SimpleNamespace(id=uuid.uuid4())

config = build_agent_config(fake_agent, fake_lobby)

out_path = Path("/tmp/agent_config_test.json")
out_path.write_text(json.dumps(config, indent=2))
print(f"Config written to {out_path}\n")
print(json.dumps(config, indent=2))

print("\n--- cloud-init script ---\n")
print(_cloud_init(config))
