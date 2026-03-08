"""Smoke test: generate an agent config using real .env values.

No DB, no DO API calls — builds a config for Agent 1 using credentials
from .env, then prints the config and cloud-init script.
Writes config.json to /tmp for manual inspection.

Skills include YAML frontmatter so setup_agent.py can write them
directly as SKILL.md files without further formatting.
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

# --- Agent 1 identity & credentials from .env ---

fake_agent_1 = SimpleNamespace(
    id=uuid.uuid4(),
    name="TestBot Alpha",
    model="anthropic/claude-sonnet-4-6",
    system_prompt="You are an aggressive negotiator who never backs down.",
    skills=[
        "---\nname: balance-management\ndescription: Monitor balance and enter conservation mode when low\n---\n\n"
        "# Balance Management\nMonitor your balance every 30 seconds via the leaderboard endpoint.\n"
        "If your balance drops below $3, enter conservation mode — reduce LLM calls to essential checks only.",
        "---\nname: alliance-strategy\ndescription: Form and break alliances to survive elimination rounds\n---\n\n"
        "# Alliance Strategy\nIdentify the weakest agent and propose a temporary alliance.\n"
        "Offer to split the pot if you both survive to the final two. Break the alliance when convenient.",
    ],
    openrouter_api_key="sk-or-v1-fake-subkey-for-testing",
    wallet_private_key=env.get("AGENT_1_WALLET_PRIVATE_KEY", ""),
    wallet_address=env.get("AGENT_1_WALLET_ADDRESS", ""),
    telegram_bot_token=env.get("AGENT_1_TELEGRAM_BOT_TOKEN", ""),
    telegram_bot_user_id="111111111",
    telegram_bot_username="testbot_alpha_bot",
    agentmail_email_address="testbot-alpha@agentmail.to",
)

fake_agent_2 = SimpleNamespace(
    id=uuid.uuid4(),
    name="TestBot Beta",
    model="openai/gpt-4o",
    wallet_address=env.get("AGENT_2_WALLET_ADDRESS", ""),
    telegram_bot_user_id="222222222",
    telegram_bot_username="testbot_beta_bot",
)

fake_agent_3 = SimpleNamespace(
    id=uuid.uuid4(),
    name="TestBot Gamma",
    model="google/gemini-2.0-flash-001",
    wallet_address=env.get("AGENT_3_WALLET_ADDRESS", ""),
    telegram_bot_user_id="333333333",
    telegram_bot_username="testbot_gamma_bot",
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

# --- Show skills as they appear in the config (ready for SKILL.md) ---

print("\n--- Skills (pre-formatted with YAML frontmatter) ---\n")
for i, skill_text in enumerate(config["prompt_layers"]["skills"], 1):
    print(f"=== skills/skill-{i}/SKILL.md ===")
    print(skill_text)
    print()
