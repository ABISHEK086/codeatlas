from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import github
from ..config import settings
from ..db import get_db
from ..models import User
from ..security import (
    COOKIE_NAME, SESSION_DAYS, create_token, decode_token, get_current_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/github/login")
def github_login():
    if not settings.github_client_id:
        raise HTTPException(500, "GITHUB_CLIENT_ID is not set in .env")
    state = create_token("oauth", purpose="state", minutes=10)  # CSRF protection
    params = urlencode({
        "client_id": settings.github_client_id,
        "redirect_uri": f"{settings.backend_url}/auth/github/callback",
        "scope": "read:user public_repo",  # use "repo" if you want private repos
        "state": state,
    })
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")


@router.get("/github/callback")
def github_callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        decode_token(state, "state")
    except jwt.PyJWTError:
        raise HTTPException(400, "Invalid or expired OAuth state")

    try:
        token = github.exchange_code(code)
        gh = github.get_user(token)
    except Exception as e:
        raise HTTPException(400, f"GitHub login failed: {e}")

    user = db.scalar(select(User).where(User.github_id == gh["id"]))
    if user is None:
        user = User(github_id=gh["id"], login=gh["login"],
                    avatar_url=gh.get("avatar_url"), access_token=token)
        db.add(user)
    else:
        user.login, user.avatar_url, user.access_token = gh["login"], gh.get("avatar_url"), token
    db.commit()

    session = create_token(str(user.id), purpose="session", minutes=SESSION_DAYS * 24 * 60)
    response = RedirectResponse(settings.frontend_url)
    response.set_cookie(
        COOKIE_NAME, session, httponly=True, samesite="lax",
        secure=False,  # set True when deployed on HTTPS
        max_age=SESSION_DAYS * 86400,
    )
    return response


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "login": user.login, "avatar_url": user.avatar_url}


@router.post("/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME)
    return response