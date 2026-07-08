"""Generate a Telethon StringSession for deployment without a .session file.

Run this LOCALLY (it needs interactive phone/2FA input):

    python scripts/generate_string_session.py

Copy the printed string and set it as an environment variable on your server:

    TELEGRAM_STRING_SESSION_TELEVAULT=<the printed string>

The variable name follows the pattern:
    TELEGRAM_STRING_SESSION_<SESSION_NAME_UPPERCASED>

So if your TELEGRAM_SESSION_NAMES=televault (the default), the var is
TELEGRAM_STRING_SESSION_TELEVAULT.

For multiple sessions (pooling):
    TELEGRAM_SESSION_NAMES=acc1,acc2
    TELEGRAM_STRING_SESSION_ACC1=...
    TELEGRAM_STRING_SESSION_ACC2=...
"""

import asyncio
import sys
from pathlib import Path

# Allow running from the project root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from telethon import TelegramClient  # noqa: E402
from telethon.sessions import StringSession  # noqa: E402

from app.config import settings  # noqa: E402


async def main():
    if not settings.telegram_ready:
        print("ERROR: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env")
        sys.exit(1)

    session_name = input(
        f"Session name to generate [default: {settings.primary_session_name}]: "
    ).strip() or settings.primary_session_name

    print(f"\nLogging in as session '{session_name}' …")
    async with TelegramClient(StringSession(), settings.api_id_int, settings.telegram_api_hash) as client:
        await client.start()
        string = client.session.save()

    env_var = f"TELEGRAM_STRING_SESSION_{session_name.upper()}"
    print("\n" + "=" * 70)
    print("SUCCESS — add this to your server's environment variables:")
    print(f"\n  {env_var}={string}\n")
    print("Keep this value secret — it grants full access to your Telegram account.")
    print("=" * 70)


asyncio.run(main())
