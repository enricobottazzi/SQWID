"""
run_agent.py

Usage:
    python3 run_agent.py [agent_config.json]

What it does:
    1. Runs setup_openclaw_agent() to build the local config + workspace
    2. Creates a fresh DigitalOcean Droplet for this agent
    3. SSHs in, installs Node + OpenClaw
    4. Uploads openclaw.json + the agent workspace
    5. Starts the OpenClaw gateway on the remote server

Requirements:
    pip install paramiko requests

Environment variables (or set DO_API_TOKEN / DO_SSH_KEY_ID below):
    DO_API_TOKEN   — your DigitalOcean personal access token
    DO_SSH_KEY_ID  — the numeric ID of your SSH key in DigitalOcean
                     (find it at: https://cloud.digitalocean.com/account/security)
    SSH_KEY_PATH   — path to your private SSH key (default: ~/.ssh/id_rsa)
"""

import json
import os
import sys
import time
from pathlib import Path

import paramiko
import requests

import setup_agent

# ── Config ────────────────────────────────────────────────────────────────────

DO_API_TOKEN  = "dop_v1_a49ec99c1ceaff48c39558170dc9af4d8533fa18a0869cd6d386458192addc19"       # Required
DO_SSH_KEY_ID = "54675538"       # Required (numeric ID)
SSH_KEY_PATH  = os.environ.get("SSH_KEY_PATH", str(Path.home() / ".ssh" / "id_rsa"))

DO_API_BASE   = "https://api.digitalocean.com/v2"
DROPLET_SIZE  = "s-1vcpu-2gb"       # $12/mo — 2GB RAM required for OpenClaw onboarding
DROPLET_IMAGE = "ubuntu-22-04-x64"  # Ubuntu 22.04 LTS
DROPLET_REGION = "nyc3"             # Change to your preferred region


# ══════════════════════════════════════════════════════════════════════════════
# DigitalOcean API helpers
# ══════════════════════════════════════════════════════════════════════════════

def do_headers() -> dict:
    if not DO_API_TOKEN:
        raise RuntimeError("DO_API_TOKEN environment variable is not set.")
    return {
        "Authorization": f"Bearer {DO_API_TOKEN}",
        "Content-Type":  "application/json",
    }


def create_droplet(agent_name: str, agent_id: str) -> dict:
    """Create a new DigitalOcean Droplet for this agent. Returns the droplet dict."""
    if not DO_SSH_KEY_ID:
        raise RuntimeError("DO_SSH_KEY_ID environment variable is not set.")

    slug = f"sqwid-{agent_id}-{agent_name.lower().replace(' ', '-')}"[:63]
    payload = {
        "name":     slug,
        "region":   DROPLET_REGION,
        "size":     DROPLET_SIZE,
        "image":    DROPLET_IMAGE,
        "ssh_keys": [DO_SSH_KEY_ID],
        "tags":     ["sqwid", f"agent-{agent_id}"],
    }

    print(f"☁️  Creating Droplet '{slug}' on DigitalOcean...")
    resp = requests.post(f"{DO_API_BASE}/droplets", headers=do_headers(), json=payload)
    resp.raise_for_status()
    droplet = resp.json()["droplet"]
    print(f"   Droplet ID: {droplet['id']} — waiting for it to become active...")
    return droplet


def wait_for_droplet_ip(droplet_id: int, timeout: int = 180) -> str:
    """Poll until the droplet has a public IPv4. Returns the IP."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.get(f"{DO_API_BASE}/droplets/{droplet_id}", headers=do_headers())
        resp.raise_for_status()
        networks = resp.json()["droplet"]["networks"]["v4"]
        for net in networks:
            if net["type"] == "public":
                ip = net["ip_address"]
                print(f"✅ Droplet is live at {ip}")
                return ip
        print("   Still waiting for IP...")
        time.sleep(10)
    raise TimeoutError(f"Droplet {droplet_id} did not get an IP within {timeout}s")


def delete_droplet(droplet_id: int) -> None:
    """Destroy a droplet by ID."""
    requests.delete(f"{DO_API_BASE}/droplets/{droplet_id}", headers=do_headers())
    print(f"🗑️  Droplet {droplet_id} deleted.")


# ══════════════════════════════════════════════════════════════════════════════
# SSH helpers
# ══════════════════════════════════════════════════════════════════════════════

def ssh_connect(ip: str, retries: int = 12, delay: int = 15) -> paramiko.SSHClient:
    """Connect via SSH, retrying while the server boots."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.RSAKey.from_private_key_file(SSH_KEY_PATH)

    for attempt in range(1, retries + 1):
        try:
            print(f"   SSH attempt {attempt}/{retries} to {ip}...")
            client.connect(ip, username="root", pkey=key, timeout=10)
            print(f"✅ SSH connected to {ip}")
            return client
        except Exception as e:
            if attempt == retries:
                raise
            print(f"   Not ready yet ({e}), retrying in {delay}s...")
            time.sleep(delay)


def ssh_run(client: paramiko.SSHClient, cmd: str, desc: str = "", stream: bool = False) -> str:
    """Run a command over SSH. If stream=True, prints output live line-by-line."""
    if desc:
        print(f"   ▶ {desc}")
    stdin, stdout, stderr = client.exec_command(cmd, get_pty=stream)

    if stream:
        lines = []
        for line in iter(stdout.readline, ""):
            line = line.rstrip("\n").rstrip("\r")
            if line:
                print(f"     {line}", flush=True)
                lines.append(line)
        exit_code = stdout.channel.recv_exit_status()
        out = "\n".join(lines)
        err = ""
    else:
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        exit_code = stdout.channel.recv_exit_status()
        if out:
            print(f"     {out}")

    if exit_code != 0:
        raise RuntimeError(f"Command failed (exit {exit_code}): {cmd}\n{err}")
    return out


def scp_file(client: paramiko.SSHClient, local_path: Path, remote_path: str) -> None:
    """Upload a single file via SFTP."""
    sftp = client.open_sftp()
    sftp.put(str(local_path), remote_path)
    sftp.close()


def scp_dir(client: paramiko.SSHClient, local_dir: Path, remote_dir: str) -> None:
    """Recursively upload a directory via SFTP."""
    sftp = client.open_sftp()

    def _upload(local: Path, remote: str):
        try:
            sftp.mkdir(remote)
        except OSError:
            pass  # already exists
        for item in local.iterdir():
            r = f"{remote}/{item.name}"
            if item.is_dir():
                _upload(item, r)
            else:
                sftp.put(str(item), r)

    _upload(local_dir, remote_dir)
    sftp.close()
    print(f"   Uploaded {local_dir} → {remote_dir}")


# ══════════════════════════════════════════════════════════════════════════════
# Remote setup
# ══════════════════════════════════════════════════════════════════════════════

# Step 1: Install Node + OpenClaw binary only (no wizard/onboarding)
INSTALL_SCRIPT = """
set -e
export DEBIAN_FRONTEND=noninteractive

# Wait for Ubuntu's automatic first-boot apt tasks to finish
echo "Waiting for apt lock to be released..."
while fuser /var/lib/apt/lists/lock /var/lib/dpkg/lock /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
    echo "  apt is locked by another process, waiting 5s..."
    sleep 5
done
echo "apt lock released."

# Node 22 via NodeSource
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs

# Install OpenClaw npm package only — skip the onboarding wizard entirely
# by using npm install directly instead of the install.sh script
export NODE_OPTIONS="--max-old-space-size=1536"
npm install -g openclaw

# Make sure openclaw is on PATH for root
export PATH="$PATH:/root/.npm-global/bin:/usr/local/bin"
echo 'export PATH="$PATH:/root/.npm-global/bin"' >> /root/.bashrc

openclaw --version
node --version
"""


def install_openclaw(client: paramiko.SSHClient) -> None:
    print("📦 Installing Node 22 + OpenClaw on remote server...")
    ssh_run(client, INSTALL_SCRIPT, "Running install script (this takes ~2-3 mins)", stream=True)


def upload_config_and_workspace(
    client: paramiko.SSHClient,
    agent_id: str,
) -> None:
    """Upload openclaw.json and the agent workspace to the remote server."""
    # openclaw.json + auth-profiles.json (credential store with API keys)
    local_cfg = Path.home() / ".openclaw" / "openclaw.json"
    ssh_run(client, "mkdir -p /root/.openclaw", "Creating .openclaw dir")
    scp_file(client, local_cfg, "/root/.openclaw/openclaw.json")
    print("   Uploaded openclaw.json")
    local_auth = Path.home() / ".openclaw" / "agents" / agent_id / "agent" / "auth-profiles.json"
    if local_auth.exists():
        ssh_run(client, f"mkdir -p /root/.openclaw/agents/{agent_id}/agent", "Creating agent credential dir")
        scp_file(client, local_auth, f"/root/.openclaw/agents/{agent_id}/agent/auth-profiles.json")
        print(f"   Uploaded auth-profiles.json (API keys for agent {agent_id})")

    # workspace (~/clawd/<agent_id>)
    local_ws = Path.home() / "clawd" / agent_id
    ssh_run(client, f"mkdir -p /root/clawd/{agent_id}", "Creating workspace dir")
    scp_dir(client, local_ws, f"/root/clawd/{agent_id}")


# PATH prefix for all remote openclaw commands (installer may put it in ~/.npm-global)
REMOTE_PATH = 'export PATH="$PATH:/root/.npm-global/bin:/usr/local/bin"'

def start_gateway(client: paramiko.SSHClient) -> None:
    """Install and start the OpenClaw gateway as a background service."""
    print("🚀 Starting OpenClaw gateway on remote server...")
    ssh_run(client, f"{REMOTE_PATH} && openclaw doctor --fix || true", "Running doctor --fix")
    ssh_run(client, f"{REMOTE_PATH} && openclaw gateway install",       "Installing gateway service")
    ssh_run(client, f"{REMOTE_PATH} && openclaw gateway start",         "Starting gateway")
    # Give it a moment to settle
    time.sleep(5)
    status = ssh_run(client, f"{REMOTE_PATH} && openclaw gateway status 2>&1 || true", "Checking status")
    print(f"   Gateway status: {status or '(no output)'}")


# ══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════════════════

def run_agent_on_server(input_file: str = "agent_config.json") -> None:
    # ── Step 1: local setup ───────────────────────────────────────────────────
    print("="*60)
    print("STEP 1 — Local agent setup")
    print("="*60)
    setup_agent.setup_openclaw_agent(input_file)

    # Read agent_id and name from the config for naming the droplet
    with open(input_file) as f:
        raw = json.load(f)
    agent_id   = raw.get("agent_id", "main")
    agent_name = raw.get("agent_name", "agent")

    # ── Step 2: create Droplet ────────────────────────────────────────────────
    print("\n" + "="*60)
    print("STEP 2 — Provisioning cloud server (DigitalOcean)")
    print("="*60)
    droplet = create_droplet(agent_name, agent_id)
    droplet_id = droplet["id"]

    try:
        ip = wait_for_droplet_ip(droplet_id)

        # Extra wait — SSH daemon takes a moment after IP appears
        print("   Waiting 30s for SSH daemon to start...")
        time.sleep(30)

        # ── Step 3: SSH + install ─────────────────────────────────────────────
        print("\n" + "="*60)
        print("STEP 3 — Installing OpenClaw on server")
        print("="*60)
        client = ssh_connect(ip)
        install_openclaw(client)

        # ── Step 4: upload config ─────────────────────────────────────────────
        print("\n" + "="*60)
        print("STEP 4 — Uploading config and workspace")
        print("="*60)
        upload_config_and_workspace(client, agent_id)

        # ── Step 5: start gateway ─────────────────────────────────────────────
        print("\n" + "="*60)
        print("STEP 5 — Starting gateway")
        print("="*60)
        start_gateway(client)
        client.close()

        # ── Done ──────────────────────────────────────────────────────────────
        print("\n" + "="*60)
        print(f"🦞 Agent '{agent_name}' is LIVE on {ip}")
        print(f"   SSH:       ssh root@{ip}")
        print(f"   Logs:      ssh root@{ip} 'tail -f /root/.openclaw/logs/gateway.log'")
        print(f"   Destroy:   python3 -c \"import run_agent; run_agent.delete_droplet({droplet_id})\"")
        print("="*60)

    except Exception as e:
        print(f"\n❌ Error during deployment: {e}")
        print(f"   Droplet {droplet_id} is still running — destroy it manually or rerun.")
        raise


if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "agent_config.json"
    run_agent_on_server(input_file)