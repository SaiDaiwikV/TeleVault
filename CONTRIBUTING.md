# Contributing to TeleVault

Thanks for considering a contribution. This is a portfolio/educational
project, but real bug fixes, security hardening, and feature work are welcome.

## Ground rules

- **Never commit secrets.** `.env`, `*.session`, and `*.db` are gitignored —
  keep it that way. If you accidentally commit one, rotate the credential,
  don't just delete the file in a follow-up commit (it's still in history).
- **Security first.** This project's whole premise is zero-knowledge storage.
  Any change touching encryption, auth, or the Telegram storage layer should
  call out its security implications in the PR description.
- Keep PRs focused — one phase/feature per PR is easier to review than a
  grab-bag.

## Dev setup

```bash
git clone <your fork>
cd TeleVault
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # fill in TELEGRAM_API_ID / TELEGRAM_API_HASH
python scripts/check_telegram_config.py   # verify before running anything else
uvicorn app.main:app --reload

cd frontend
npm install
npm run dev                # served at http://localhost:5173, proxied to the API
```

## Before opening a PR

- Run `python scripts/check_telegram_config.py` if you touched anything in
  `app/telegram_storage.py`.
- `python -m py_compile app/*.py` at minimum; a linter (ruff) config is
  included — `ruff check .` if you have it installed.
- For frontend changes: `npm run build` should succeed with no errors.
- Update `README.md` / `SECURITY.md` if you change the threat model, add an
  endpoint, or add a config variable (and reflect it in `.env.example`).

## Reporting a security issue

Please don't open a public issue for a vulnerability. See `SECURITY.md` for
the current threat model and open a private report (GitHub Security
Advisories) instead.
