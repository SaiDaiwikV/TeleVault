import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)


class Settings:
    app_name = "TeleVault"
    environment = os.getenv("TELEVAULT_ENV", "development")
    database_url = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'televault.db'}")
    telegram_api_id = os.getenv("TELEGRAM_API_ID", "")
    telegram_api_hash = os.getenv("TELEGRAM_API_HASH", "")

    # One or more comma-separated session names for multi-account/session
    # pooling (Phase 4). Each session is a separate Telegram login that can
    # upload in round-robin, spreading load below Telegram's flood limits.
    _raw_sessions = os.getenv("TELEGRAM_SESSION_NAMES") or os.getenv("TELEGRAM_SESSION_NAME", "televault")
    telegram_session_names = [s.strip() for s in _raw_sessions.split(",") if s.strip()]

    # String sessions: set TELEGRAM_STRING_SESSION_<NAME>=<string> to avoid
    # needing a .session file on the server (required for Railway / Render / any
    # platform without a persistent filesystem).
    # Example for the default "televault" session:
    #   TELEGRAM_STRING_SESSION_TELEVAULT=1BVtsOKABu...
    # Generate the value locally with: python scripts/generate_string_session.py
    @property
    def telegram_string_sessions(self) -> dict[str, str]:
        result = {}
        for name in self.telegram_session_names:
            key = f"TELEGRAM_STRING_SESSION_{name.upper()}"
            val = os.getenv(key, "").strip()
            if val:
                result[name] = val
        return result

    telegram_storage_channel_id = os.getenv("TELEGRAM_STORAGE_CHANNEL_ID", "").strip()
    chunk_size = int(os.getenv("TELEVAULT_CHUNK_SIZE", str(16 * 1024 * 1024)))
    token_ttl_days = int(os.getenv("TELEVAULT_TOKEN_TTL_DAYS", "30"))

    # Hard ceiling on a single upload (bytes) so one request can't exhaust the
    # server's scratch disk. Default 2 GiB, matching Telethon's per-file limit
    # for a non-Premium account. Set to 0 to disable the check.
    max_upload_bytes = int(os.getenv("TELEVAULT_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))

    # Comma-separated list of allowed browser origins for CORS. Empty in
    # production means "same-origin only" (the SPA is served by this app).
    cors_origins = [o.strip() for o in os.getenv("TELEVAULT_CORS_ORIGINS", "").split(",") if o.strip()]

    # Auth rate limiting: N attempts per window per IP+username.
    auth_rate_limit_attempts = int(os.getenv("TELEVAULT_AUTH_RATE_LIMIT", "10"))
    auth_rate_limit_window_seconds = int(os.getenv("TELEVAULT_AUTH_RATE_WINDOW", "300"))

    # Share links
    share_link_default_hours = int(os.getenv("TELEVAULT_SHARE_DEFAULT_HOURS", "24"))
    share_link_max_hours = int(os.getenv("TELEVAULT_SHARE_MAX_HOURS", "720"))  # 30 days

    scratch_dir = Path(os.getenv("TELEVAULT_SCRATCH_DIR", str(BASE_DIR / ".scratch")))

    # ── OAuth social login ────────────────────────────────────────────────
    # Public base URL of this app — required for building OAuth callback URLs.
    # Example: https://televault.example.com  (no trailing slash)
    app_base_url = os.getenv("TELEVAULT_APP_BASE_URL", "http://localhost:8000")

    # Google OAuth 2.0  (https://console.cloud.google.com → Credentials)
    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")

    # GitHub OAuth App  (https://github.com/settings/developers)
    github_client_id = os.getenv("GITHUB_CLIENT_ID", "")
    github_client_secret = os.getenv("GITHUB_CLIENT_SECRET", "")

    @property
    def telegram_ready(self) -> bool:
        return bool(self.telegram_api_id and self.telegram_api_hash)

    @property
    def api_id_int(self) -> int:
        return int(self.telegram_api_id)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"prod", "production"}

    @property
    def primary_session_name(self) -> str:
        return self.telegram_session_names[0]

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def github_enabled(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret)


settings = Settings()
settings.scratch_dir.mkdir(parents=True, exist_ok=True)
