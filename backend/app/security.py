from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

ALGORITHM = "HS256"
COOKIE_NAME = "session"
SESSION_DAYS = 7


def create_token(subject: str, purpose: str, minutes: int) -> str:
    payload = {
        "sub": subject,
        "purpose": purpose,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str, purpose: str) -> str:
    """Returns the subject, or raises jwt.PyJWTError."""
    data = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    if data.get("purpose") != purpose:
        raise jwt.InvalidTokenError("wrong token purpose")
    return data["sub"]


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        user_id = int(decode_token(token, "session"))
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, "Invalid or expired session")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(401, "User not found")
    return user