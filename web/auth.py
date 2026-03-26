"""
Authentication helpers for Lectionary Engines.
Session = signed cookie (itsdangerous). No JWT, no Redis.
"""

import os
from typing import Optional

from fastapi import Request, Depends
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

# ── Config ───────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-please")
COOKIE_NAME = "le_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

# ── Crypto ───────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(SECRET_KEY, salt="le-session")

# ── Public routes (no login required) ───────────────────────
PUBLIC_PATHS = {"/login", "/logout", "/health", "/favicon.ico"}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_session_cookie(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})


def decode_session_cookie(token: str) -> Optional[int]:
    try:
        data = serializer.loads(token, max_age=COOKIE_MAX_AGE)
        return data.get("user_id")
    except (BadSignature, SignatureExpired):
        return None


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Return the logged-in User, or None if not authenticated."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    user_id = decode_session_cookie(token)
    if not user_id:
        return None
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    return user


def require_login(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency — redirects to /login if not authenticated."""
    user = get_current_user(request, db)
    if not user:
        raise _LoginRedirect(request.url.path)
    return user


class _LoginRedirect(Exception):
    def __init__(self, next_path: str = "/"):
        self.next_path = next_path
