import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import TeamSession, TeamUser


COOKIE_NAME = "mip_session"
SECURE_COOKIE = os.getenv("MIP_SECURE_COOKIE", "false").lower() == "true"
APP_ORIGIN = (os.getenv("MIP_ORIGIN") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def password_digest(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=2**15, r=8, p=3, maxmem=64 * 1024**2, dklen=32
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"{salt.hex()}:{password_digest(password, salt).hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    salt, expected = (stored or ("00" * 16 + ":" + "00" * 32)).split(":")
    actual = password_digest(password, bytes.fromhex(salt))
    return hmac.compare_digest(actual, bytes.fromhex(expected)) and stored is not None


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def same_origin(request: Request):
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    expected = APP_ORIGIN or f"{request.url.scheme}://{request.url.netloc}"
    if origin is not None and origin != expected:
        raise HTTPException(status_code=403, detail="Cross-origin request rejected")
    if request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}:
        raise HTTPException(status_code=403, detail="Cross-origin request rejected")


def current_user(request: Request, db: Session = Depends(get_db)) -> TeamUser:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        user = db.scalar(
            select(TeamUser)
            .join(TeamSession)
            .where(
                TeamSession.token_hash == token_digest(token),
                TeamSession.expires_at > datetime.now(timezone.utc),
                TeamUser.is_active.is_(True),
            )
        )
        if user is not None:
            return user
    raise HTTPException(status_code=401, detail="Sign in to continue")


def require_staff(user: TeamUser = Depends(current_user)) -> TeamUser:
    if user.role == "customer":
        raise HTTPException(status_code=403, detail="Staff access required")
    return user


def require_team_access(request: Request, user: TeamUser = Depends(require_staff)):
    if request.method not in SAFE_METHODS and user.role not in {"admin", "editor"}:
        raise HTTPException(status_code=403, detail="Editor or administrator access required")


def require_admin(user: TeamUser = Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
