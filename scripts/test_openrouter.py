#!/usr/bin/env python3
"""Smoke-test the OpenRouter provisioning API from .env.

Exercises the full lifecycle: create key → verify initial state → top-up → verify
updated state → cleanup.

Usage:
    source .venv/bin/activate
    python scripts/test_openrouter.py
"""

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://openrouter.ai/api/v1"


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def create_key(api_key: str) -> dict | None:
    """Create a sub-key with limit=0. Returns {"key": ..., "hash": ..., "data": ...}."""
    resp = httpx.post(
        f"{BASE_URL}/keys",
        headers=_headers(api_key),
        json={"name": "squid-smoke-test", "limit": 0},
    )
    if resp.status_code not in (200, 201):
        print(f"  FAILED — could not create key: HTTP {resp.status_code}: {resp.text[:300]}")
        return None
    body = resp.json()
    key = body.get("key")
    data = body.get("data", {})
    key_hash = data.get("hash")
    if not key or not key_hash:
        print(f"  FAILED — unexpected response shape: {body}")
        return None
    print(f"  Key created: hash={key_hash}")
    return {"key": key, "hash": key_hash, "data": data}


def get_key_details(api_key: str, key_hash: str) -> dict | None:
    """GET /keys/{hash} and return the data object."""
    resp = httpx.get(
        f"{BASE_URL}/keys/{key_hash}",
        headers=_headers(api_key),
    )
    if resp.status_code != 200:
        print(f"  FAILED — could not fetch key details: HTTP {resp.status_code}: {resp.text[:300]}")
        return None
    return resp.json().get("data")


def update_limit(api_key: str, key_hash: str, new_limit: float) -> bool:
    """PATCH /keys/{hash} to set spending limit to an absolute value."""
    resp = httpx.patch(
        f"{BASE_URL}/keys/{key_hash}",
        headers=_headers(api_key),
        json={"limit": new_limit},
    )
    if resp.status_code != 200:
        print(f"  FAILED — could not update limit: HTTP {resp.status_code}: {resp.text[:300]}")
        return False
    return True


def delete_key(api_key: str, key_hash: str) -> bool:
    """DELETE /keys/{hash} for cleanup."""
    resp = httpx.delete(
        f"{BASE_URL}/keys/{key_hash}",
        headers=_headers(api_key),
    )
    if resp.status_code == 200:
        print(f"  Key {key_hash} deleted (cleanup OK)")
        return True
    print(f"  Cleanup WARNING — could not delete key: HTTP {resp.status_code}: {resp.text[:200]}")
    return False


def print_key_state(data: dict) -> None:
    """Pretty-print the fields we care about."""
    print(f"    spending limit : {data.get('limit')}")
    print(f"    credits        : {data.get('limit_remaining')}")
    print(f"    total spent    : {data.get('usage')}")


def assert_key_state(data: dict, expected_limit, expected_credits, expected_usage) -> bool:
    ok = True
    if data.get("limit") != expected_limit:
        print(f"  FAILED — expected spending limit={expected_limit}, got {data.get('limit')}")
        ok = False
    if data.get("limit_remaining") != expected_credits:
        print(f"  FAILED — expected credits={expected_credits}, got {data.get('limit_remaining')}")
        ok = False
    if data.get("usage") != expected_usage:
        print(f"  FAILED — expected total spent={expected_usage}, got {data.get('usage')}")
        ok = False
    if ok:
        print("  OK — all values match.")
    return ok


def main():
    print("=== OpenRouter Smoke Test ===\n")

    api_key = os.environ.get("OPENROUTER_PROVISIONING_KEY", "")
    if not api_key or api_key.startswith("your-"):
        print("  SKIPPED — OPENROUTER_PROVISIONING_KEY is not set in .env")
        print()
        _print_setup_instructions()
        sys.exit(1)

    key_hash = None
    ok = True

    try:
        # --- 1. Create a sub-key with limit=0 ---
        print("--- 1. Create sub-key (limit=0) ---")
        result = create_key(api_key)
        if not result:
            sys.exit(1)
        key_hash = result["hash"]

        # --- 2. Verify initial state: limit=0, credits=0, usage=0 ---
        print("\n--- 2. Verify initial state ---")
        data = get_key_details(api_key, key_hash)
        if data is None:
            sys.exit(1)
        print_key_state(data)
        if not assert_key_state(data, expected_limit=0, expected_credits=0, expected_usage=0):
            ok = False

        # --- 3. Top-up: set spending limit to $1.50 ---
        print("\n--- 3. Top-up: set spending limit to $1.50 ---")
        if not update_limit(api_key, key_hash, 1.50):
            ok = False
        else:
            print("  Spending limit set to $1.50")

        # --- 4. Verify state after top-up ---
        print("\n--- 4. Verify state after top-up ---")
        data = get_key_details(api_key, key_hash)
        if data is None:
            ok = False
        else:
            print_key_state(data)
            if not assert_key_state(data, expected_limit=1.5, expected_credits=1.5, expected_usage=0):
                ok = False

    finally:
        # --- 5. Cleanup ---
        if key_hash:
            print("\n--- 5. Cleanup (delete test key) ---")
            delete_key(api_key, key_hash)

    if ok:
        print("\nAll checks passed. OpenRouter provisioning integration is working.")
    else:
        print("\nSome checks failed — see above.")
        sys.exit(1)


def _print_setup_instructions():
    print("HOW TO SET UP OPENROUTER:")
    print("=" * 50)
    print()
    print("Step 1: Create an account")
    print("  - Go to https://openrouter.ai/")
    print("  - Sign up and add credits to your account")
    print()
    print("Step 2: Get a provisioning (management) key")
    print("  - Go to https://openrouter.ai/settings/keys")
    print("  - Create a new key with management permissions")
    print()
    print("Step 3: Add the key to your .env")
    print("  OPENROUTER_PROVISIONING_KEY=sk-or-v1-...")
    print()
    print("Then re-run: python scripts/test_openrouter.py")


if __name__ == "__main__":
    main()
