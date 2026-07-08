import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import AuthToken, User


security = HTTPBearer(auto_error=False)

# OWASP-recommended floor for PBKDF2-HMAC-SHA256 (2023+). Stored hashes encode
# the iteration count they were created with, so verify_password stays
# backward-compatible with any older 260k hashes already in the DB.
PBKDF2_ITERATIONS = 600_000


def _hash_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        # OAuth-only account — no local password set.
        return False
    try:
        scheme, iterations, salt, expected = password_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations),
        ).hex()
        return hmac.compare_digest(digest, expected)
    except ValueError:
        return False


def issue_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(40)
    db.add(
        AuthToken(
            user_id=user.id,
            token_hash=_hash_hex(token),
            expires_at=datetime.utcnow() + timedelta(days=settings.token_ttl_days),
        )
    )
    db.commit()
    return token


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token_hash = _hash_hex(credentials.credentials)
    token = db.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash))
    if token is None or token.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = db.get(User, token.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token user")
    return user
