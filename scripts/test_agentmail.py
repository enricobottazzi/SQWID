#!/usr/bin/env python3
"""Smoke-test the AgentMail API key and inbox creation from .env.

Usage:
    source .venv/bin/activate
    python scripts/test_agentmail.py
"""

import os
import random
import string
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

API = "https://api.agentmail.to/v0"


def check_api_key(api_key: str, pod_id: str) -> bool:
    """List inboxes to verify the API key and pod are valid. Returns True on success."""
    resp = httpx.get(
        f"{API}/pods/{pod_id}/inboxes",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if resp.status_code == 401:
        print("  FAILED — API key is invalid (401 Unauthorized)")
        return False
    if resp.status_code != 200:
        print(f"  FAILED — HTTP {resp.status_code}: {resp.text[:300]}")
        return False
    print("  API key OK — authenticated successfully")
    return True


def create_test_inbox(api_key: str, pod_id: str) -> dict | None:
    """Create a throwaway inbox and return its details, or None on failure."""
    resp = httpx.post(
        f"{API}/pods/{pod_id}/inboxes",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"username": f"smoke-test-{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}"},
    )
    if resp.status_code not in (200, 201):
        print(f"  FAILED — could not create inbox: HTTP {resp.status_code}: {resp.text[:300]}")
        return None
    data = resp.json()
    inbox_id = data.get("inbox_id")
    if not inbox_id:
        print(f"  FAILED — unexpected response shape (no inbox_id): {data}")
        return None
    print(f"  Inbox created: {inbox_id}")
    return {"inbox_id": inbox_id}


def delete_inbox(api_key: str, pod_id: str, inbox_id: str) -> bool:
    """Delete an inbox by ID. Returns True on success."""
    resp = httpx.delete(
        f"{API}/pods/{pod_id}/inboxes/{inbox_id}",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if resp.status_code in (200, 202, 204):
        print(f"  Inbox {inbox_id} deleted (cleanup OK)")
        return True
    print(f"  Cleanup WARNING — could not delete inbox: HTTP {resp.status_code}: {resp.text[:200]}")
    return False


def main():
    print("=== AgentMail Smoke Test ===\n")

    api_key = os.environ.get("AGENTMAIL_API_KEY", "")
    pod_id = os.environ.get("AGENTMAIL_POD_ID", "")
    if not api_key or api_key.startswith("your-"):
        print("  SKIPPED — AGENTMAIL_API_KEY is not set in .env")
        print()
        _print_setup_instructions()
        sys.exit(1)
    if not pod_id or pod_id.startswith("your-"):
        print("  SKIPPED — AGENTMAIL_POD_ID is not set in .env")
        print()
        _print_setup_instructions()
        sys.exit(1)

    print("--- 1. Validate API key and pod ---")
    if not check_api_key(api_key, pod_id):
        print()
        _print_setup_instructions()
        sys.exit(1)

    print("\n--- 2. Create a test inbox ---")
    inbox = create_test_inbox(api_key, pod_id)
    if not inbox:
        sys.exit(1)

    print("\n--- 3. Cleanup (delete test inbox) ---")
    delete_inbox(api_key, pod_id, inbox["inbox_id"])

    print("\nAll checks passed. AgentMail integration is working.")


def _print_setup_instructions():
    print("HOW TO SET UP AGENTMAIL:")
    print("=" * 50)
    print()
    print("Step 1: Create an account")
    print("  - Go to https://console.agentmail.to/")
    print("  - Sign up for a free account")
    print()
    print("Step 2: Get your API key")
    print("  - In the AgentMail console, navigate to API Keys")
    print("  - Create a new key and copy it")
    print()
    print("Step 3: Get your Pod ID")
    print("  - In the console, open your pod (or create one) and copy its ID")
    print()
    print("Step 4: Add to your .env")
    print("  AGENTMAIL_API_KEY=your-api-key-here")
    print("  AGENTMAIL_POD_ID=your-pod-id-here")
    print()
    print("Then re-run: python scripts/test_agentmail.py")


if __name__ == "__main__":
    main()
