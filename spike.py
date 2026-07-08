#!/usr/bin/env python3
"""
TeleVault — Phase 0 Spike
=========================
Proves the core assumption behind the whole project:
    1. Authenticate to Telegram via MTProto (Telethon).
    2. Ensure a PRIVATE channel exists to act as the raw storage backend.
    3. Upload a file — splitting it into chunks if it exceeds the per-file cap.
    4. Record only the returned message_id(s)  (this is the "metadata" a real
       app would keep in a database).
    5. Download the chunks back by message_id and re-assemble them.
    6. Verify the SHA-256 hash matches the original  ->  integrity proven.

If this script prints "SPIKE PASSED", the entire TeleVault idea is viable.

Usage:
    pip install -r requirements.txt
    cp .env.example .env      # then fill in api_id / api_hash  (already done)
    python spike.py                 # uploads a generated 12 MB test file
    python spike.py /path/to/file   # uploads a real file of your choice

First run will prompt for your phone number + the Telegram login code
(and 2FA password if you have one). A local `televault.session` file is
then reused so you won't log in again.
"""

import asyncio
import hashlib
import os
import sys
import tempfile

from dotenv import load_dotenv, set_key
from telethon import TelegramClient
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.errors import FloodWaitError

# ── Config ────────────────────────────────────────────────────────────────
load_dotenv()

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "televault")
STORAGE_CHANNEL_ID = os.getenv("TELEGRAM_STORAGE_CHANNEL_ID", "").strip()
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

# Telethon (MTProto) supports up to 2 GB/file (4 GB w/ Premium). We chunk well
# below that so the reassembly logic is exercised even on small test files.
# For the spike we use a small chunk size on purpose so a ~12 MB file splits
# into several parts and the ordering/reassembly path is actually tested.
CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB per chunk (tune upward for real use)

if not API_ID or not API_HASH or API_ID == "your_api_id_here":
    sys.exit("ERROR: Set TELEGRAM_API_ID and TELEGRAM_API_HASH in your .env file.")

API_ID = int(API_ID)


# ── Helpers ───────────────────────────────────────────────────────────────
def sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def human(nbytes: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TiB"


async def get_storage_channel(client: TelegramClient):
    """Return the storage channel entity, creating a private one if needed.

    In a real app this ID lives in config/DB. For the spike we create one on
    first run and persist its ID back into .env so subsequent runs reuse it.
    """
    global STORAGE_CHANNEL_ID
    if STORAGE_CHANNEL_ID:
        try:
            return await client.get_entity(int(STORAGE_CHANNEL_ID))
        except Exception as e:
            print(f"  (could not reuse stored channel {STORAGE_CHANNEL_ID}: {e})")

    print("  Creating a new PRIVATE storage channel 'TeleVault-Storage' ...")
    result = await client(CreateChannelRequest(
        title="TeleVault-Storage",
        about="Private raw-storage backend for TeleVault. Do not post here manually.",
        megagroup=False,  # broadcast channel
    ))
    channel = result.chats[0]
    # Telethon channel IDs are used as -100<id> in the bot world; get_entity
    # from the returned object works directly, so we persist the peer id.
    chan_id = channel.id
    STORAGE_CHANNEL_ID = str(chan_id)
    try:
        set_key(ENV_PATH, "TELEGRAM_STORAGE_CHANNEL_ID", STORAGE_CHANNEL_ID)
        print(f"  Saved channel id {chan_id} to .env for future runs.")
    except Exception as e:
        print(f"  (warning: could not write channel id to .env: {e})")
    return channel


async def upload_file_chunked(client, channel, path):
    """Split `path` into CHUNK_SIZE parts, upload each, return ordered msg ids."""
    size = os.path.getsize(path)
    total_chunks = max(1, (size + CHUNK_SIZE - 1) // CHUNK_SIZE)
    print(f"  File is {human(size)} -> {total_chunks} chunk(s) of "
          f"{human(CHUNK_SIZE)} max")

    message_ids = []
    with open(path, "rb") as f:
        for idx in range(total_chunks):
            data = f.read(CHUNK_SIZE)
            # Write chunk to a temp file so Telethon can upload it as a document.
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".part{idx}") as tmp:
                tmp.write(data)
                tmp_path = tmp.name
            try:
                msg = await client.send_file(
                    channel,
                    tmp_path,
                    caption=f"chunk {idx + 1}/{total_chunks}",
                    force_document=True,
                )
                message_ids.append(msg.id)
                print(f"    uploaded chunk {idx + 1}/{total_chunks} "
                      f"-> message_id {msg.id}")
            except FloodWaitError as e:
                print(f"    rate-limited, sleeping {e.seconds}s ...")
                await asyncio.sleep(e.seconds)
                msg = await client.send_file(channel, tmp_path,
                                             caption=f"chunk {idx + 1}/{total_chunks}",
                                             force_document=True)
                message_ids.append(msg.id)
            finally:
                os.unlink(tmp_path)
    return message_ids


async def download_and_reassemble(client, channel, message_ids, out_path):
    """Fetch each chunk message in order and concatenate into out_path."""
    print(f"  Downloading {len(message_ids)} chunk(s) and reassembling ...")
    with open(out_path, "wb") as out:
        for i, msg_id in enumerate(message_ids):
            message = await client.get_messages(channel, ids=msg_id)
            if message is None or message.media is None:
                raise RuntimeError(f"chunk message {msg_id} missing or has no media")
            chunk_bytes = await client.download_media(message, file=bytes)
            out.write(chunk_bytes)
            print(f"    reassembled chunk {i + 1}/{len(message_ids)} "
                  f"(from message_id {msg_id})")


# ── Main spike flow ───────────────────────────────────────────────────────
async def main():
    # Decide what to upload.
    if len(sys.argv) > 1:
        source_path = sys.argv[1]
        if not os.path.isfile(source_path):
            sys.exit(f"ERROR: no such file: {source_path}")
        cleanup_source = False
    else:
        # Generate a ~12 MB random test file so chunking is exercised.
        print("No file given — generating a 12 MB random test file ...")
        source_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "testfile_original.bin")
        with open(source_path, "wb") as f:
            f.write(os.urandom(12 * 1024 * 1024))
        cleanup_source = False  # keep it so you can inspect; gitignored anyway

    original_hash = sha256_of_file(source_path)
    print(f"Source file : {source_path}")
    print(f"SHA-256     : {original_hash}")
    print("-" * 60)

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()  # prompts for phone/code on first run
    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (@{me.username})")
    print("-" * 60)

    channel = await get_storage_channel(client)
    print("-" * 60)

    print("STEP 1/3  Uploading ...")
    message_ids = await upload_file_chunked(client, channel, source_path)
    print(f"  -> metadata to store in DB: {message_ids}")
    print("-" * 60)

    print("STEP 2/3  Downloading + reassembling ...")
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "downloaded_result.bin")
    await download_and_reassemble(client, channel, message_ids, out_path)
    print("-" * 60)

    print("STEP 3/3  Verifying integrity ...")
    result_hash = sha256_of_file(out_path)
    print(f"  original  SHA-256: {original_hash}")
    print(f"  roundtrip SHA-256: {result_hash}")
    print("-" * 60)

    await client.disconnect()

    if result_hash == original_hash:
        print("✅ SPIKE PASSED — upload, chunking, download, and reassembly all work.")
        print("   The TeleVault concept is viable. Proceed to build the full app.")
    else:
        print("❌ SPIKE FAILED — hashes differ. Investigate chunk ordering / reassembly.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
