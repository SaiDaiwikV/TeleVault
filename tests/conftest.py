"""Shared pytest fixtures for the backend test suite.

The suite runs with **zero external dependencies** — no real Telegram account,
no network. Two things make that possible:

* An isolated SQLite database per test, created in a temp dir and wired in by
  overriding the ``get_db`` dependency.
* A fake ``TelegramStorage`` that keeps "uploaded" chunk bytes in an in-memory
  dict instead of talking to MTProto, so upload/download/delete flows exercise
  the real application code end-to-end without a live channel.
"""
import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """The auth rate limiter is a module-level singleton; clear its state
    between tests so accumulated attempts from earlier tests don't bleed in."""
    from app.security import auth_rate_limiter

    auth_rate_limiter._hits.clear()
    yield
    auth_rate_limiter._hits.clear()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # ── isolated database ────────────────────────────────────────────────
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}, future=True
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app import db as db_module
    from app.db import Base

    # Point the app's engine/session at the throwaway DB before creating tables.
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestingSessionLocal)
    Base.metadata.create_all(bind=engine)

    from app import main as main_module

    monkeypatch.setattr(main_module, "SessionLocal", TestingSessionLocal)

    # ── fake Telegram storage ────────────────────────────────────────────
    fake = FakeStorage()
    monkeypatch.setattr(main_module, "storage", fake)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    from app.db import get_db

    main_module.app.dependency_overrides[get_db] = override_get_db
    with TestClient(main_module.app) as test_client:
        test_client.fake_storage = fake
        yield test_client
    main_module.app.dependency_overrides.clear()


@pytest.fixture()
def auth_client(client):
    """A TestClient already registered + carrying a valid bearer token."""
    resp = client.post("/api/auth/register", json={"username": "alice", "password": "supersecret"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


class _UploadedChunk:
    """Mirrors telegram_storage.UploadedChunk's shape (attribute access)."""

    def __init__(self, order, tg_message_id, size, sha256):
        self.order = order
        self.tg_message_id = tg_message_id
        self.size = size
        self.sha256 = sha256


class FakeStorage:
    """In-memory stand-in for TelegramStorage.

    Splits an uploaded file into chunks the same way the real storage does,
    stores each chunk's bytes under a synthetic "message id", and serves them
    back on download so the full upload → persist → download → integrity path
    is covered without a live Telegram channel.
    """

    def __init__(self, chunk_size: int = 1024):
        self.chunk_size = chunk_size
        self._messages: dict[int, bytes] = {}
        self._next_id = 1

    async def check_config(self):
        return {"ok": True, "account": "fake", "channel_id": 1, "channel_title": "fake"}

    async def upload_path(self, path, caption_prefix):
        uploaded = []
        order = 0
        with open(path, "rb") as fh:
            while True:
                data = fh.read(self.chunk_size)
                if not data:
                    break
                mid = self._next_id
                self._next_id += 1
                self._messages[mid] = data
                uploaded.append(
                    _UploadedChunk(order, mid, len(data), hashlib.sha256(data).hexdigest())
                )
                order += 1
        if not uploaded:
            mid = self._next_id
            self._next_id += 1
            self._messages[mid] = b""
            uploaded.append(_UploadedChunk(0, mid, 0, hashlib.sha256(b"").hexdigest()))
        return uploaded

    async def download_messages(self, chunks):
        for message_id, expected_sha256 in chunks:
            data = self._messages.get(message_id)
            if data is None:
                raise RuntimeError(f"missing message {message_id}")
            yield data

    async def delete_messages(self, message_ids):
        for mid in message_ids:
            self._messages.pop(mid, None)

    async def disconnect(self):
        pass
