import logging
from datetime import datetime

from . import github
from .config import settings
from .db import SessionLocal
from .models import Commit, CommitFile, File, Repository
from .analyze import analyze_repo

log = logging.getLogger("codeatlas.ingest")

MAX_FILE_BYTES = 200_000
MAX_FILES = 2000

IGNORED_DIRS = {
    ".git", "node_modules", "dist", "build", ".next", "venv", ".venv",
    "__pycache__", "vendor", "target", ".idea", ".vscode", "coverage",
}
IGNORED_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock"}

LANGUAGES = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".sql": "sql",
    ".md": "markdown", ".rst": "markdown", ".txt": "text",
    ".json": "json", ".yml": "yaml", ".yaml": "yaml", ".toml": "toml",
}
TEST_DIRS = {"test", "tests", "__tests__", "spec"}
TEST_SUFFIXES = (
    "_test.py", ".test.ts", ".test.tsx", ".test.js", ".test.jsx",
    ".spec.ts", ".spec.tsx", ".spec.js",
)


def classify(path: str) -> tuple[str | None, str] | None:
    """Return (language, kind), or None if the file should be skipped."""
    parts = path.split("/")
    name = parts[-1]
    if name in IGNORED_NAMES or any(p in IGNORED_DIRS for p in parts[:-1]):
        return None
    dot = name.rfind(".")
    ext = name[dot:].lower() if dot != -1 else ""
    language = LANGUAGES.get(ext)
    if language is None:
        return None

    lower = name.lower()
    if ext in (".md", ".rst", ".txt"):
        kind = "doc"
    elif (
        any(p.lower() in TEST_DIRS for p in parts[:-1])
        or lower.startswith("test_")
        or lower.endswith(TEST_SUFFIXES)
    ):
        kind = "test"
    elif ext in (".json", ".yml", ".yaml", ".toml"):
        kind = "config"
    else:
        kind = "source"
    return language, kind


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def ingest_repo(repo_id: int, token: str) -> None:
    """Runs in a background task, so it opens its own DB session."""
    db = SessionLocal()
    try:
        repo = db.get(Repository, repo_id)
        repo.status, repo.error = "indexing", None
        db.commit()

        # Re-indexing: clear old data (cascades handle the child tables)
        db.query(Commit).filter(Commit.repo_id == repo.id).delete()
        db.query(File).filter(File.repo_id == repo.id).delete()
        db.commit()

        # ---- files ----
        zf = github.download_zip(token, repo.owner, repo.name, repo.default_branch)
        path_to_id: dict[str, int] = {}
        pending: list[File] = []

        for info in zf.infolist():
            if info.is_dir() or info.file_size > MAX_FILE_BYTES:
                continue
            if "/" not in info.filename:
                continue
            rel = info.filename.split("/", 1)[1]  # strip "owner-repo-sha/"
            meta = classify(rel)
            if meta is None:
                continue
            try:
                text = zf.read(info).decode("utf-8")
            except UnicodeDecodeError:
                continue
            if "\x00" in text:
                continue
            pending.append(File(
                repo_id=repo.id, path=rel, language=meta[0], kind=meta[1], content=text,
            ))
            if len(pending) >= MAX_FILES:
                break

        db.add_all(pending)
        db.flush()
        for f in pending:
            path_to_id[f.path] = f.id
        db.commit()

        try:
            analyze_repo(db, repo.id)
        except Exception:
            log.exception("analysis failed; continuing without it")
            db.rollback()

        # ---- commits (best effort: don't fail the whole index) ----
        try:
            for item in github.list_commits(token, repo.owner, repo.name, settings.max_commits):
                detail = github.get_commit(token, repo.owner, repo.name, item["sha"])
                meta = detail["commit"]
                commit = Commit(
                    repo_id=repo.id,
                    sha=detail["sha"],
                    message=meta["message"],
                    author=(meta.get("author") or {}).get("name"),
                    committed_at=_parse_date((meta.get("author") or {}).get("date")),
                )
                db.add(commit)
                db.flush()
                for changed in detail.get("files", []):
                    file_id = path_to_id.get(changed["filename"])
                    if file_id:
                        db.add(CommitFile(commit_id=commit.id, file_id=file_id))
            db.commit()
        except Exception:
            log.exception("commit history fetch failed; continuing without it")
            db.rollback()

        repo = db.get(Repository, repo_id)
        repo.status = "ready"
        db.commit()
    except Exception as e:
        log.exception("ingest failed")
        db.rollback()
        repo = db.get(Repository, repo_id)
        if repo:
            repo.status, repo.error = "failed", str(e)[:500]
            db.commit()
    finally:
        db.close()