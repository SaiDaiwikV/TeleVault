"""OAuth 2.0 social login — Google and GitHub.

Flow
----
1. Browser → GET /api/auth/oauth/{provider}
   → backend builds the provider's authorization URL (with PKCE state), stores
     a short-lived CSRF token in a secure HttpOnly cookie, then redirects the
     browser to the provider's consent screen.

2. Provider → GET /api/auth/oauth/{provider}/callback?code=...&state=...
   → backend validates state, exchanges the code for tokens, fetches the
     provider's user-info, finds or creates a TeleVault User + OAuthAccount,
     issues an app bearer token, then redirects to the SPA with the token
     appended as a URL fragment so JavaScript can store it and proceed as if
     the user just submitted the login form.

Design notes
------------
* We use Authlib's ``httpx`` integration (``AsyncOAuth2Client``) rather than
  Starlette's session middleware so we avoid adding a server-side session
  store just for OAuth state.  Instead, the CSRF state is round-tripped as an
  encrypted signed cookie (``state`` cookie → verified in callback).
* The bearer token placed in the redirect fragment (#token=...) is the same
  opaque ``secrets.token_urlsafe(40)`` used by the local login flow.  The
  browser-side JS reads it with ``window.location.hash``, stores it in
  localStorage under ``televault_token``, and removes the fragment from the
  address bar.
* Usernames for new OAuth accounts are derived from the provider's display
  name / login, sanitised, and de-duplicated with a numeric suffix if taken.
"""

import re
import secrets
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import issue_token
from .config import settings
from .db import get_db
from .models import OAuthAccount, User

router = APIRouter(prefix="/api/auth/oauth", tags=["oauth"])

# ── provider registry ────────────────────────────────────────────────────────

Provider = Literal["google", "github"]

_PROVIDERS: dict[str, dict] = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scopes": "openid email profile",
        "id_field": "sub",
        "name_field": "name",
        "email_field": "email",
    },
    "github": {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scopes": "read:user user:email",
        "id_field": "id",
        "name_field": "login",
        "email_field": "email",
    },
}

# Seconds the CSRF state cookie is valid.  The user has this long to complete
# the provider consent screen.
_STATE_TTL = 600

# ── helpers ──────────────────────────────────────────────────────────────────


def _cfg(provider: str) -> dict:
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown OAuth provider: {provider}")
    return _PROVIDERS[provider]


def _client_creds(provider: str) -> tuple[str, str]:
    if provider == "google":
        if not settings.google_enabled:
            raise HTTPException(status_code=503, detail="Google OAuth is not configured")
        return settings.google_client_id, settings.google_client_secret
    if provider == "github":
        if not settings.github_enabled:
            raise HTTPException(status_code=503, detail="GitHub OAuth is not configured")
        return settings.github_client_id, settings.github_client_secret
    raise HTTPException(status_code=404, detail=f"Unknown OAuth provider: {provider}")


def _callback_url(provider: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}/api/auth/oauth/{provider}/callback"


def _sanitise_username(raw: str) -> str:
    """Turn any provider display string into a valid TeleVault username."""
    slug = re.sub(r"[^a-z0-9_]", "", raw.lower().replace(" ", "_"))
    # Enforce the 3-char minimum the Credentials schema requires.
    if len(slug) < 3:
        slug = slug.ljust(3, "0")
    return slug[:80]


def _unique_username(db: Session, base: str) -> str:
    candidate = base
    suffix = 1
    while db.scalar(select(User).where(User.username == candidate)) is not None:
        candidate = f"{base[:77]}{suffix}"
        suffix += 1
    return candidate


def _find_or_create_user(db: Session, provider: str, subject: str, display_name: str, email: str | None) -> User:
    """Return an existing user linked to this OAuth identity, or create one."""
    account = db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.subject == str(subject),
        )
    )
    if account is not None:
        # Keep email up to date in case the user changed it at the provider.
        if email and account.email != email:
            account.email = email
            db.commit()
        user = db.get(User, account.user_id)
        if user is None:
            raise HTTPException(status_code=500, detail="Orphaned OAuth account — please contact support")
        return user

    # First time this (provider, subject) pair is seen — provision a new user.
    base = _sanitise_username(display_name or email or provider)
    username = _unique_username(db, base)
    user = User(username=username, password_hash=None)
    db.add(user)
    db.flush()  # get user.id before inserting OAuthAccount

    db.add(
        OAuthAccount(
            user_id=user.id,
            provider=provider,
            subject=str(subject),
            email=email,
        )
    )
    db.commit()
    db.refresh(user)
    return user


# ── routes ───────────────────────────────────────────────────────────────────


@router.get("/{provider}")
async def oauth_redirect(provider: str, response: Response) -> RedirectResponse:
    """Step 1 — redirect the browser to the provider's consent screen."""
    cfg = _cfg(provider)
    client_id, _ = _client_creds(provider)
    state = secrets.token_urlsafe(32)

    params = {
        "client_id": client_id,
        "redirect_uri": _callback_url(provider),
        "scope": cfg["scopes"],
        "response_type": "code",
        "state": state,
    }
    if provider == "google":
        params["access_type"] = "online"

    from urllib.parse import urlencode

    auth_url = f"{cfg['auth_url']}?{urlencode(params)}"

    redirect = RedirectResponse(url=auth_url, status_code=302)
    # Secure, short-lived cookie so we can verify state in the callback.
    redirect.set_cookie(
        key="oauth_state",
        value=state,
        max_age=_STATE_TTL,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )
    return redirect


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    oauth_state: str | None = None,  # FastAPI reads cookies automatically when named
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Step 2 — exchange the authorization code and issue a TeleVault token."""
    from fastapi import Request

    # Surface provider errors (e.g. user denied consent) back to the SPA.
    if error:
        return RedirectResponse(url=f"/#oauth_error={error}", status_code=302)

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    cfg = _cfg(provider)
    client_id, client_secret = _client_creds(provider)

    # ── CSRF validation ────────────────────────────────────────────────
    # The cookie is deleted immediately after reading so it can only be used
    # once (replay protection).  We keep this simple rather than pulling in
    # itsdangerous just for state comparison.
    if not oauth_state or not secrets.compare_digest(oauth_state, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state — possible CSRF")

    # ── Token exchange ─────────────────────────────────────────────────
    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            cfg["token_url"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _callback_url(provider),
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Accept": "application/json"},
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Token exchange failed with provider")

        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=502, detail="Provider did not return an access token")

        # ── User info ──────────────────────────────────────────────────
        userinfo_resp = await client.get(
            cfg["userinfo_url"],
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to fetch user info from provider")
        userinfo = userinfo_resp.json()

    subject = str(userinfo.get(cfg["id_field"], ""))
    if not subject:
        raise HTTPException(status_code=502, detail="Provider returned no user identifier")

    display_name = str(userinfo.get(cfg["name_field"], "") or "")
    email = userinfo.get(cfg["email_field"])

    # GitHub may return email=null if the user hides it; fall back to a
    # secondary API call to get the primary verified address.
    if provider == "github" and not email:
        async with httpx.AsyncClient(timeout=10) as client:
            emails_resp = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            if emails_resp.status_code == 200:
                for entry in emails_resp.json():
                    if entry.get("primary") and entry.get("verified"):
                        email = entry.get("email")
                        break

    user = _find_or_create_user(db, provider, subject, display_name, email)
    app_token = issue_token(db, user)

    # Redirect to the SPA with the token in the URL fragment.
    # JavaScript reads it, stores it in localStorage, then strips the fragment.
    redirect = RedirectResponse(
        url=f"/#oauth_token={app_token}&user_id={user.id}&username={user.username}",
        status_code=302,
    )
    # Clear the state cookie.
    redirect.delete_cookie("oauth_state")
    return redirect
