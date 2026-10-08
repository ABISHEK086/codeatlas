import re

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import github
from ..db import get_db
from ..ingest import ingest_repo
from ..models import Commit, File, Repository, User
from ..security import get_current_user

router = APIRouter(prefix="/repos", tags=["repos"])

FULL_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ConnectRepo(BaseModel):
    full_name: str  # "owner/name"

    @field_validator("full_name")
    @classmethod
    def check(cls, v: str) -> str:
        v = v.strip().removeprefix("https://github.com/").strip("/")
        if not FULL_NAME.match(v):
            raise ValueError("Use the format owner/name")
        return v


def _summary(repo: Repository, db: Session) -> dict:
    kinds = dict(db.execute(
        select(File.kind, func.count()).where(File.repo_id == repo.id).group_by(File.kind)
    ).all())
    commits = db.scalar(select(func.count()).select_from(Commit).where(Commit.repo_id == repo.id))
    return {
        "id": repo.id,
        "full_name": f"{repo.owner}/{repo.name}",
        "default_branch": repo.default_branch,
        "status": repo.status,
        "error": repo.error,
        "files": sum(kinds.values()),
        "files_by_kind": kinds,
        "commits": commits,
    }


def _owned_repo(repo_id: int, user: User, db: Session) -> Repository:
    repo = db.get(Repository, repo_id)
    if not repo or repo.user_id != user.id:
        raise HTTPException(404, "Repository not found")
    return repo


@router.post("", status_code=202)
def connect_repo(
    body: ConnectRepo,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    owner, name = body.full_name.split("/")
    try:
        meta = github.get_repo(user.access_token, owner, name)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(404, "Repo not found, or it is private and the token lacks access")
        raise HTTPException(502, f"GitHub error: {e.response.status_code}")

    repo = db.scalar(select(Repository).where(
        Repository.user_id == user.id,
        Repository.owner == meta["owner"]["login"],
        Repository.name == meta["name"],
    ))
    if repo is None:
        repo = Repository(user_id=user.id, owner=meta["owner"]["login"], name=meta["name"])
        db.add(repo)
    repo.default_branch = meta["default_branch"]
    repo.status = "pending"
    db.commit()

    background.add_task(ingest_repo, repo.id, user.access_token)
    return _summary(repo, db)


@router.get("")
def list_repos(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repos = db.scalars(select(Repository).where(Repository.user_id == user.id)
                       .order_by(Repository.id.desc())).all()
    return [_summary(r, db) for r in repos]


@router.get("/{repo_id}")
def get_repo_status(repo_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    return _summary(_owned_repo(repo_id, user, db), db)


@router.get("/{repo_id}/files")
def list_files(repo_id: int, kind: str | None = None,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = _owned_repo(repo_id, user, db)
    q = select(File.id, File.path, File.language, File.kind).where(File.repo_id == repo.id)
    if kind:
        q = q.where(File.kind == kind)
    rows = db.execute(q.order_by(File.path)).all()
    return [{"id": r.id, "path": r.path, "language": r.language, "kind": r.kind} for r in rows]