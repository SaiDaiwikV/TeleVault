import asyncio
import hashlib
import itertools
import os
import tempfile
from pathlib import Path
from typing import AsyncIterator, NamedTuple

from dotenv import set_key
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import CreateChannelRequest, DeleteMessagesRequest

from .config import ENV_PATH, settings


class UploadedChunk(NamedTuple):
    order: int
    tg_message_id: int
    size: int
    sha256: str


class ChunkIntegrityError(RuntimeError):
    """Raised when a downloaded chunk's hash doesn't match its recorded hash."""


class TelegramConfigError(RuntimeError):
    """Raised when Telegram credentials are missing or invalid."""


async def _with_flood_retry(coro_factory, max_retries: int = 3):
    """Run an async call, transparently retrying on Telegram FloodWaitError."""
    attempt = 0
    while True:
        try:
            return await coro_factory()
        except FloodWaitError as exc:
            attempt += 1
            if attempt > max_retries:
                raise
            await asyncio.sleep(exc.seconds)


class TelegramStorage:
    """Talks to Telegram over MTProto (via Telethon).

    Supports a pool of one or more sessions (Phase 4: session pooling) so
    upload traffic can be spread across multiple logins to stay further below
    Telegram's per-account flood limits. All sessions must be members/owners
    of the same private storage channel.
    """

    def __init__(self) -> None:
        self._clients: dict[str, TelegramClient] = {}
        self._channel = None
        self._lock = asyncio.Lock()
        self._rotation = itertools.cycle(settings.telegram_session_names)

    async def _client_for(self, session_name: str) -> TelegramClient:
        if not settings.telegram_ready:
            raise TelegramConfigError("TELEGRAM_API_ID and TELEGRAM_API_HASH are required")
        async with self._lock:
            client = self._clients.get(session_name)
            if client is None:
                # Prefer a string session from the environment (deployment-friendly —
                # no .session file needed on the server) over a file-based session.
                string_session = settings.telegram_string_sessions.get(session_name)
                session = StringSession(string_session) if string_session else session_name
                client = TelegramClient(session, settings.api_id_int, settings.telegram_api_hash)
                await client.start()
                if not await client.is_user_authorized():
                    await client.disconnect()
                    raise TelegramConfigError(
                        f"Telegram session '{session_name}' is not authorized. "
                        "Run `python scripts/check_telegram_config.py` to log in interactively."
                    )
                self._clients[session_name] = client
            return client

    async def client(self) -> TelegramClient:
        """The primary (first-configured) session, used for reads/deletes/channel ops."""
        return await self._client_for(settings.primary_session_name)

    async def next_upload_client(self) -> TelegramClient:
        """Round-robins across the configured session pool for uploads."""
        session_name = next(self._rotation)
        return await self._client_for(session_name)

    async def channel(self):
        if self._channel is not None:
            return self._channel
        client = await self.client()
        if settings.telegram_storage_channel_id:
            try:
                self._channel = await client.get_entity(int(settings.telegram_storage_channel_id))
                return self._channel
            except Exception:
                self._channel = None

        result = await client(
            CreateChannelRequest(
                title="TeleVault-Storage",
                about="Private raw-storage backend for TeleVault. Do not post here manually.",
                megagroup=False,
            )
        )
        self._channel = result.chats[0]
        set_key(str(ENV_PATH), "TELEGRAM_STORAGE_CHANNEL_ID", str(self._channel.id))
        settings.telegram_storage_channel_id = str(self._channel.id)
        return self._channel

    async def check_config(self) -> dict:
        """Non-destructive pre-flight check: credentials valid, channel reachable.

        Meant to be called before the app accepts uploads (see /api/telegram/check
        and scripts/check_telegram_config.py) so misconfiguration is caught with a
        clear message instead of failing mid-upload.
        """
        if not settings.telegram_ready:
            return {
                "ok": False,
                "reason": "missing_credentials",
                "detail": "TELEGRAM_API_ID / TELEGRAM_API_HASH are not set in .env",
            }
        try:
            client = await self.client()
        except TelegramConfigError as exc:
            return {"ok": False, "reason": "not_authorized", "detail": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": "connection_failed", "detail": str(exc)}

        try:
            me = await client.get_me()
            channel = await self.channel()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": "channel_unreachable", "detail": str(exc)}

        pool_status = []
        for name in settings.telegram_session_names:
            try:
                c = await self._client_for(name)
                pool_status.append({"session": name, "authorized": await c.is_user_authorized()})
            except Exception as exc:  # noqa: BLE001
                pool_status.append({"session": name, "authorized": False, "error": str(exc)})

        return {
            "ok": True,
            "account": getattr(me, "username", None) or getattr(me, "first_name", "unknown"),
            "channel_id": getattr(channel, "id", None),
            "channel_title": getattr(channel, "title", None),
            "session_pool": pool_status,
        }

    async def upload_path(self, path: Path, caption_prefix: str) -> list[UploadedChunk]:
        channel = await self.channel()
        uploaded: list[UploadedChunk] = []
        order = 0
        with path.open("rb") as source:
            while True:
                data = source.read(settings.chunk_size)
                if not data:
                    break
                digest = hashlib.sha256(data).hexdigest()
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".part{order}") as tmp:
                    tmp.write(data)
                    tmp_path = tmp.name
                try:
                    client = await self.next_upload_client()
                    msg = await _with_flood_retry(
                        lambda: client.send_file(
                            channel, tmp_path, caption=f"{caption_prefix} chunk {order + 1}", force_document=True
                        )
                    )
                    uploaded.append(UploadedChunk(order, msg.id, len(data), digest))
                    order += 1
                finally:
                    os.unlink(tmp_path)
        if not uploaded:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".empty") as tmp:
                tmp_path = tmp.name
            try:
                client = await self.next_upload_client()
                msg = await _with_flood_retry(
                    lambda: client.send_file(channel, tmp_path, caption=f"{caption_prefix} empty file", force_document=True)
                )
                uploaded.append(UploadedChunk(0, msg.id, 0, hashlib.sha256(b"").hexdigest()))
            finally:
                os.unlink(tmp_path)
        return uploaded

    async def download_messages(
        self, chunks: list[tuple[int, str]]
    ) -> AsyncIterator[bytes]:
        """Download chunk messages in order, verifying each against its stored sha256.

        `chunks` is a list of (tg_message_id, expected_sha256) pairs so a
        corrupted or tampered chunk is caught before it reaches the client
        instead of silently reassembling into a bad file (Phase 4 integrity
        checking).
        """
        channel = await self.channel()
        client = await self.client()
        for message_id, expected_sha256 in chunks:
            message = await _with_flood_retry(lambda: client.get_messages(channel, ids=message_id))
            if message is None or message.media is None:
                raise RuntimeError(f"Telegram chunk message {message_id} is missing")
            data = await _with_flood_retry(lambda: client.download_media(message, file=bytes))
            if expected_sha256 and hashlib.sha256(data).hexdigest() != expected_sha256:
                raise ChunkIntegrityError(
                    f"Chunk message {message_id} failed integrity check (hash mismatch)"
                )
            yield data

    async def delete_messages(self, message_ids: list[int]) -> None:
        if not message_ids:
            return
        channel = await self.channel()
        client = await self.client()
        await _with_flood_retry(
            lambda: client(DeleteMessagesRequest(channel=channel, id=message_ids))
        )

    async def disconnect(self) -> None:
        for client in self._clients.values():
            await client.disconnect()


storage = TelegramStorage()
