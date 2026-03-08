"""Smoke test for sandbox management: launch a droplet, poll until running, terminate."""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.basicConfig(level=logging.INFO)

from app.services.sandbox import get_sandbox_status, launch_sandbox, terminate_sandbox


async def main():
    print("Launching sandbox...")
    result = await launch_sandbox("test-123", "test-agent")
    droplet_id = result["droplet_id"]
    print(f"Droplet created: {droplet_id}")

    print("Polling status...")
    for _ in range(12):
        status = await get_sandbox_status(droplet_id)
        print(f"  Status: {status}")
        if status == "running":
            break
        await asyncio.sleep(10)
    else:
        print("Droplet did not reach 'running' in time")

    print("Terminating sandbox...")
    await terminate_sandbox(droplet_id)
    print("Done")


if __name__ == "__main__":
    asyncio.run(main())
