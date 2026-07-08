#!/usr/bin/env python3
"""Run this before starting the server (and before any upload) to confirm
Telegram is configured correctly.

    python scripts/check_telegram_config.py

It will:
  1. Verify TELEGRAM_API_ID / TELEGRAM_API_HASH are set.
  2. Log in each configured session (prompting for phone/code on first run,
     same as the spike), so `.session` files exist before the server starts.
  3. Confirm/create the private storage channel.
  4. Print a clear PASS/FAIL summary.

Exits non-zero on failure so it can be used as a CI/deploy gate, e.g.:
    python scripts/check_telegram_config.py && uvicorn app.main:app
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.telegram_storage import storage  # noqa: E402


async def main() -> int:
    print("== TeleVault / Telegram configuration check ==\n")

    if not settings.telegram_ready:
        print("FAIL: TELEGRAM_API_ID and TELEGRAM_API_HASH are not set.")
        print("      Get them from https://my.telegram.org -> API development tools,")
        print("      then copy .env.example to .env and fill them in.")
        return 1

    print(f"Sessions configured: {', '.join(settings.telegram_session_names)}")
    print("Connecting (you may be prompted for phone number + login code on first run)...\n")

    result = await storage.check_config()
    await storage.disconnect()

    if not result["ok"]:
        print(f"FAIL: {result['reason']}")
        print(f"      {result['detail']}")
        return 1

    print(f"PASS: authenticated as {result['account']}")
    print(f"      storage channel: {result['channel_title']} (id={result['channel_id']})")
    print("      session pool:")
    for s in result["session_pool"]:
        status = "authorized" if s.get("authorized") else f"NOT authorized ({s.get('error', 'unknown error')})"
        print(f"        - {s['session']}: {status}")

    if not settings.telegram_storage_channel_id:
        print("\nNote: TELEGRAM_STORAGE_CHANNEL_ID was just created and saved to .env.")

    print("\nTelegram is configured correctly. Safe to start the server / accept uploads.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
