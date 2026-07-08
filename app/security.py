import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds baseline hardening headers to every response.

    Not a substitute for TLS termination / a reverse proxy in production, but
    closes off the cheap, common browser-side footguns by default.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'",
        )
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


class _RateLimiter:
    """Simple sliding-window rate limiter keyed by (client_ip, identifier).

    In-memory only — fine for a single-process MVP deployment. A multi-worker
    or multi-instance deployment should replace this with a shared store
    (e.g. Redis) before relying on it for real protection.

    Buckets are evicted once they fully age out, so a long-running process
    that sees many distinct IP+username keys (e.g. a brute-force sweep) does
    not accumulate empty deques indefinitely.
    """

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    def _evict_expired(self, now: float) -> None:
        """Drop keys whose most recent hit is older than the window."""
        stale = [
            key
            for key, bucket in self._hits.items()
            if not bucket or now - bucket[-1] > self.window_seconds
        ]
        for key in stale:
            del self._hits[key]

    def check(self, key: str) -> None:
        now = time.monotonic()
        # Opportunistic sweep: cheap relative to the auth work that follows,
        # and bounds memory without needing a background task.
        self._evict_expired(now)
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Please wait before trying again.",
            )
        bucket.append(now)


auth_rate_limiter = _RateLimiter(settings.auth_rate_limit_attempts, settings.auth_rate_limit_window_seconds)


def enforce_auth_rate_limit(request: Request, username: str) -> None:
    client_ip = request.client.host if request.client else "unknown"
    auth_rate_limiter.check(f"{client_ip}:{username.lower()}")
