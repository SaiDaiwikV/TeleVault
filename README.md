# TeleVault

A zero-knowledge cloud storage system that uses **Telegram (via MTProto)** as
an encrypted object-storage backend — effectively unlimited storage, backed by
your own private Telegram channel.

> **Status:** Phases 0–3 complete, Phase 4 (hardening) in progress. FastAPI +
> SQLite/PostgreSQL metadata + Telegram-backed chunk storage + a React/Tailwind
> Drive-like frontend, all with browser-side AES-256-GCM encryption.

## How it works

1. Files are uploaded into a **private Telegram channel** that acts as raw storage.
2. Large files are **split into chunks**, each sent as a separate message.
3. A **metadata layer** (SQLAlchemy models) records the folder tree and the
   ordered chunk → `message_id` mapping.
4. Every chunk is **AES-256-GCM encrypted in the browser** before upload — the
   vault passphrase never leaves the client, so neither the FastAPI backend
   nor Telegram ever sees plaintext.
5. On download, chunks are fetched by ID, their SHA-256 is verified against
   the recorded hash, reassembled, and decrypted client-side.

## Architecture

```
┌───────────────┐   REST/JSON   ┌───────────┐   MTProto   ┌──────────────────┐
│ React + Tailwind │ ───────────▶ │  FastAPI  │ ──────────▶ │ Telegram private │
│  (Drive-like UI) │ ◀─────────── │  backend  │ ◀────────── │ channel (bytes)  │
└───────────────┘               └─────┬─────┘             └──────────────────┘
                                       │
                                 ┌─────▼─────┐
                                 │ SQLite /   │  folders / files / chunks /
                                 │ PostgreSQL │  users / share links
                                 └───────────┘
```

Encryption happens entirely in the browser tab (Web Crypto API). The server
only ever handles ciphertext, hashes, and message IDs.

## Quick start

```bash
git clone <this repo>
cd TeleVault
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # add your api_id / api_hash from my.telegram.org

# Always run this before your first launch (and any time Telegram config
# changes) — it logs each session in and confirms the storage channel works,
# so misconfiguration is caught up front instead of mid-upload.
python scripts/check_telegram_config.py

uvicorn app.main:app --reload
```

Then build the frontend (served by FastAPI as a single deployable unit):

```bash
cd frontend
npm install
npm run build      # outputs to ../static/app, picked up automatically
```

For frontend development with hot reload, run `npm run dev` instead (proxies
`/api` to `http://127.0.0.1:8000`) and open `http://localhost:5173`.

Open `http://127.0.0.1:8000`, register a local account, set a vault
passphrase, and start uploading. The pre-flight banner at the top of the app
calls `GET /api/telegram/check` and blocks uploads until Telegram is
confirmed reachable.

The original spike is still available for a minimal end-to-end proof:

```bash
python spike.py /path/to/any/file
```

## Running the tests

The backend suite is hermetic — it uses a throwaway SQLite DB and an in-memory
fake for Telegram, so no API credentials or network access are needed:

```bash
pip install -r requirements-dev.txt
pytest                       # backend: auth, files/folders, dedup, share links…

cd frontend && npm test      # frontend: vitest smoke + component tests
```

Both suites run automatically in CI on every push and pull request.

## Feature overview

**Storage & transport**
- Chunked upload/download over Telethon (MTProto), chunk size configurable.
- Multi-session pooling (`TELEGRAM_SESSION_NAMES`) to spread uploads across
  more than one Telegram login and stay further below flood-wait limits.
- Automatic retry with backoff on `FloodWaitError` for uploads, downloads,
  and deletes.
- SHA-256 integrity verification per chunk on download/reassembly.
- Content-addressed deduplication: re-uploading identical ciphertext reuses
  existing Telegram messages instead of re-sending them.

**API / data layer**
- SQLite by default; set `DATABASE_URL` to a PostgreSQL DSN for multi-user
  deployment (`postgresql+psycopg2://user:pass@host:5432/televault`).
- Bearer-token auth (PBKDF2-HMAC-SHA256 password hashing, 30-day tokens).
- Auth rate limiting (per IP+username sliding window) against brute force.
- Nested folders: create, rename, move, delete (delete refuses non-empty).
- File rename, move, search, delete (Telegram messages cleaned up too, unless
  still referenced by a deduplicated copy).
- Resumable uploads: `POST /api/uploads/init` → ordered `PUT .../chunk` →
  `POST .../complete`, so an interrupted upload resumes from the last
  acknowledged byte offset instead of restarting.
- Shareable links: revocable, optionally time- and download-limited, handing
  out ciphertext only — the recipient still needs the vault passphrase.
- Security response headers (CSP, X-Frame-Options, etc.) on every response.

**Frontend**
- React + Tailwind, Drive-like file browser: folder navigation, breadcrumbs,
  search, drag-and-drop upload with progress, per-file share/rename/move/delete.
- Every file shows a deterministic "seal" — a small fingerprint swatch derived
  from its SHA-256, so identical/duplicated files are visually recognizable
  at a glance.
- Telegram configuration is checked on load and surfaced as a banner; uploads
  are disabled with a clear reason until it's fixed.

## Security model

See [`SECURITY.md`](SECURITY.md) for the full threat model. Summary:

- Credentials live only in `.env` (gitignored) — never hardcoded, never logged.
- AES-256-GCM encryption happens in the browser; the passphrase is never
  transmitted or stored server-side.
- A leaked metadata DB or compromised Telegram account yields ciphertext +
  message IDs, not plaintext, as long as the vault passphrase stays secret.
- Share links only ever distribute ciphertext.

## Roadmap

- [x] **Phase 0** — Spike: auth, chunked upload, download, integrity check
- [x] **Phase 1** — FastAPI + SQLite, real upload/download endpoints, auth
- [x] **Phase 2** — Drive-like UI: nested folders, rename/delete, search
- [x] **Phase 3** — Client-side AES-256 encryption, share links, dedup
- [x] React + Tailwind frontend
- [x] PostgreSQL support (`DATABASE_URL`)
- [x] Resumable uploads
- [x] **Phase 4** — Flood-wait handling, session pooling, chunk integrity checks
- [x] Automated test suite — backend `pytest` (auth, files/folders, dedup,
      share links, ownership isolation, header/rate-limit units) + frontend
      `vitest`, both run in CI
- [ ] Encrypted filenames (currently only file contents are encrypted)
- [ ] Thumbnails for images
- [ ] Convergent (deterministic) encryption so client-side dedup can trigger
      across identical plaintext (today each upload uses a fresh salt/IV, so
      dedup only catches byte-identical re-uploads of the same ciphertext)

## Contributing

Contributions welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md) for dev setup
and expectations, especially around never committing secrets.

## ⚠️ Disclaimer

Using Telegram purely as bulk storage may conflict with Telegram's Terms of
Service and is intended here as an **educational / portfolio project**, not a
production service.

---

Built by **Sai Daiwik V** — cybersecurity student & analyst. MIT licensed,
see [`LICENSE`](LICENSE).
