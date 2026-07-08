# TeleVault Security Model

TeleVault is a zero-knowledge storage experiment: file contents are encrypted
in the browser before they ever reach the backend, and Telegram receives only
ciphertext chunks.

## Cryptography

- Browser uploads use **AES-256-GCM** through the Web Crypto API.
- Keys are derived per-file from the user's vault passphrase with
  **PBKDF2-HMAC-SHA256**, 310,000 iterations, a fresh random 16-byte salt and
  12-byte IV per file.
- The vault passphrase is never sent to the FastAPI backend and never stored
  anywhere server-side.
- Each chunk's plaintext (ciphertext, from the server's perspective) SHA-256
  is recorded and re-verified on every download before being handed to the
  client, so a corrupted or tampered Telegram message is caught immediately
  instead of silently corrupting the reassembled file.

## Account & transport security

- Account passwords are hashed with PBKDF2-HMAC-SHA256 (260,000 iterations,
  random salt) — separate from, and unrelated to, the vault passphrase.
- Bearer tokens are random 40-byte URL-safe strings, stored server-side only
  as their SHA-256 hash, with a configurable TTL (default 30 days).
- Auth endpoints are rate-limited per IP+username to slow brute forcing.
- Every response carries baseline hardening headers (CSP, X-Frame-Options,
  X-Content-Type-Options, Referrer-Policy); HSTS is added automatically when
  `TELEVAULT_ENV=production`.
- Deploy behind TLS (a reverse proxy such as Caddy/nginx, or a platform LB) —
  this app does not terminate TLS itself.

## Sharing

- Share links are random 32-byte tokens, stored only as their SHA-256 hash,
  optionally time-limited and download-limited, and revocable at any time.
- A share link only ever serves ciphertext. The vault passphrase must be
  communicated to the recipient through a separate, trusted channel.

## Threat model

**Telegram account or storage channel compromised:** attacker reads chunk
messages and message IDs — ciphertext only.

**Metadata DB leaked:** attacker learns filenames, folder structure, sizes,
ciphertext/chunk hashes, encryption salts/IVs, Telegram message IDs, and
issued share-link hashes. They still need the vault passphrase to decrypt
contents, and share-link tokens (not just their hashes) to use a link.

**Both Telegram and the metadata DB leaked:** attacker has enough material to
attempt offline passphrase guessing against captured ciphertext. Strong,
unique vault passphrases are the load-bearing defense here — there is no
recovery mechanism if a passphrase is lost or guessed.

**Web app or browser compromised during upload/download:** plaintext can be
exposed before encryption or after decryption. This is endpoint compromise,
outside the zero-knowledge storage boundary, and no server-side control can
fully mitigate it.

**Malicious or coerced server operator:** can serve tampered frontend JS to
capture passphrases at the point of entry (this is inherent to any
browser-based zero-knowledge design, not unique to TeleVault). Running your
own instance from source, and verifying the frontend build, is the mitigation.

## Not yet hardened

- No password reset or account recovery model.
- No encrypted filename mode — names and folder structure are visible in the
  metadata DB even though contents are not.
- No delegated/wrapped key sharing (share links distribute ciphertext, not
  keys) — recipients need the passphrase out-of-band.
- Rate limiting is in-memory and per-process; a multi-worker or multi-instance
  deployment should move it to a shared store (e.g. Redis) before relying on
  it.
- No automated security test suite yet (see README roadmap).

## Reporting a vulnerability

Please do not open a public GitHub issue for a security vulnerability. Use
GitHub's private security-advisory reporting on this repository instead.
