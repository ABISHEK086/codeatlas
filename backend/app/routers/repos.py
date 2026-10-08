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
from ..analyze import analyze_repo
from .. import graph as graph_lib
from ..models import Commit, File, Repository, Symbol, User
from ..indexer import index_repo, search_repo
from ..impact import analyze_impact

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

@router.post("/{repo_id}/analyze")
def analyze(repo_id: int, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    repo = _owned_repo(repo_id, user, db)
    if repo.status != "ready":
        raise HTTPException(409, "Repository is not ready yet")
    return analyze_repo(db, repo.id)


@router.get("/{repo_id}/files/{file_id}/symbols")
def file_symbols(repo_id: int, file_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    repo = _owned_repo(repo_id, user, db)
    file = db.get(File, file_id)
    if not file or file.repo_id != repo.id:
        raise HTTPException(404, "File not found")
    rows = db.scalars(select(Symbol).where(Symbol.file_id == file.id)
                      .order_by(Symbol.start_line)).all()
    return [{"name": s.name, "kind": s.kind, "start_line": s.start_line,
             "end_line": s.end_line} for s in rows]


@router.get("/{repo_id}/graph")
def get_graph(repo_id: int, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    repo = _owned_repo(repo_id, user, db)
    g = graph_lib.build_graph(db, repo.id)
    return {
        "nodes": [{"id": n, **d} for n, d in g.nodes(data=True)],
        "edges": [{"source": u, "target": v, "kind": d["kind"]}
                  for u, v, d in g.edges(data=True)],
    }


@router.get("/{repo_id}/dependents")
def get_dependents(repo_id: int, path: str, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    repo = _owned_repo(repo_id, user, db)
    file = db.scalar(select(File).where(File.repo_id == repo.id, File.path == path))
    if not file:
        raise HTTPException(404, f"No file at path '{path}'")
    g = graph_lib.build_graph(db, repo.id)

    def describe(dist: dict[int, int]) -> list[dict]:
        rows = [{"path": g.nodes[i]["path"], "kind": g.nodes[i]["kind"], "distance": d}
                for i, d in dist.items()]
        return sorted(rows, key=lambda r: (r["distance"], r["path"]))

    affected = describe(graph_lib.dependents(g, file.id))
    return {
        "file": path,
        "direct_dependents": [r for r in affected if r["distance"] == 1],
        "all_dependents": affected,
        "affected_tests": [r for r in affected if r["kind"] == "test"],
        "depends_on": describe(graph_lib.dependencies(g, file.id)),
    }

@router.post("/{repo_id}/index")
def index(repo_id: int, user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    repo = _owned_repo(repo_id, user, db)
    if repo.status != "ready":
        raise HTTPException(409, "Repository is not ready yet")
    return index_repo(db, repo.id)


@router.get("/{repo_id}/search")
def search(repo_id: int, q: str, k: int = 5, kind: str | None = None,
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = _owned_repo(repo_id, user, db)
    return search_repo(db, repo.id, q, min(max(k, 1), 20), kind)

@router.get("/{repo_id}/impact")
def impact(repo_id: int, path: str, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    repo = _owned_repo(repo_id, user, db)
    result = analyze_impact(db, repo.id, path)
    if result is None:
        raise HTTPException(404, f"No file at path '{path}'")
    return result