import os
from typing import Optional

import bcrypt
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from config import IS_PRODUCTION
from models import User

SESSION_COOKIE = "pb_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days
_DEFAULT_SECRET = "pickleball-dev-secret-change-in-production"

_secret = os.environ.get("PB_SECRET_KEY", _DEFAULT_SECRET)
if IS_PRODUCTION and _secret == _DEFAULT_SECRET:
    raise RuntimeError("Set PB_SECRET_KEY in production (Render can generate this for you).")
_serializer = URLSafeTimedSerializer(_secret)


def session_cookie_kwargs() -> dict:
    """Cookie flags for login/logout (Secure on HTTPS hosts like Render)."""
    return {
        "httponly": True,
        "max_age": SESSION_MAX_AGE,
        "samesite": "lax",
        "secure": IS_PRODUCTION,
    }


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_session_token(user: User) -> str:
    return _serializer.dumps(
        {"user_id": user.id, "role": user.role, "username": user.username}
    )


def read_session_token(token: str) -> Optional[dict]:
    try:
        return _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def get_session_data(request: Request) -> Optional[dict]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return read_session_token(token)


def get_current_user(request: Request, db: Session) -> Optional[User]:
    data = get_session_data(request)
    if not data:
        return None
    return db.query(User).filter(User.id == data["user_id"]).first()


def require_user(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_role(request: Request, db: Session, *roles: str) -> User:
    user = require_user(request, db)
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user
