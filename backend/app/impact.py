from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import graph as graph_lib
from .models import Commit, CommitFile, File, Symbol

LEVELS = [(25, "low"), (50, "medium"), (75, "high"), (101, "critical")]


def _level(score: int) -> str:
    return next(name for limit, name in LEVELS if score < limit)


def analyze_impact(db: Session, repo_id: int, path: str) -> dict | None:
    target = db.scalar(select(File).where(File.repo_id == repo_id, File.path == path))
    if target is None:
        return None

    g = graph_lib.build_graph(db, repo_id)
    dependents = graph_lib.dependents(g, target.id)      # {file_id: distance}
    dependencies = graph_lib.dependencies(g, target.id)

    def describe(dist: dict[int, int]) -> list[dict]:
        rows = [{"path": g.nodes[i]["path"], "kind": g.nodes[i]["kind"], "distance": d}
                for i, d in dist.items()]
        return sorted(rows, key=lambda r: (r["distance"], r["path"]))

    affected = describe(dependents)
    direct = [r for r in affected if r["distance"] == 1]
    indirect = [r for r in affected if r["distance"] > 1]
    tests = [r for r in affected if r["kind"] == "test"]

    # ---- API routes in the file itself and in everything that depends on it ----
    route_rows = db.execute(
        select(Symbol.name, Symbol.start_line, File.path)
        .join(File, File.id == Symbol.file_id)
        .where(Symbol.kind == "route", Symbol.file_id.in_([target.id, *dependents]))
        .order_by(File.path, Symbol.start_line)
    ).all()
    routes = [{"route": r.name, "path": r.path, "line": r.start_line} for r in route_rows]

    # ---- history: churn and co-change ----
    commit_ids = select(CommitFile.commit_id).where(CommitFile.file_id == target.id)
    churn = db.scalar(select(func.count()).select_from(commit_ids.subquery())) or 0

    co_rows = db.execute(
        select(CommitFile.file_id, func.count().label("n"))
        .where(CommitFile.commit_id.in_(commit_ids), CommitFile.file_id != target.id)
        .group_by(CommitFile.file_id)
        .order_by(func.count().desc())
        .limit(10)
    ).all()
    linked = set(dependents) | set(dependencies)
    co_change = []
    for fid, n in co_rows:
        node = g.nodes.get(fid)
        if node is None:
            continue
        co_change.append({
            "path": node["path"],
            "times_together": n,
            "confidence": round(n / churn, 2) if churn else 0,
            "hidden_coupling": fid not in linked,   # changes together, no import link
        })

    recent = db.execute(
        select(Commit.sha, Commit.message, Commit.author, Commit.committed_at)
        .join(CommitFile, CommitFile.commit_id == Commit.id)
        .where(CommitFile.file_id == target.id)
        .order_by(Commit.committed_at.desc())
        .limit(5)
    ).all()
    recent_commits = [{
        "sha": c.sha[:7], "message": c.message.splitlines()[0][:120] if c.message else "",
        "author": c.author, "date": c.committed_at.isoformat() if c.committed_at else None,
    } for c in recent]

    # ---- risk score: transparent, rule-based ----
    factors = []

    def add(name: str, points: int, evidence: str):
        if points > 0:
            factors.append({"factor": name, "points": points, "evidence": evidence})

    add("Direct dependents", min(40, len(direct) * 8),
        f"{len(direct)} file(s) import this file directly")
    add("Indirect dependents", min(15, len(indirect) * 3),
        f"{len(indirect)} more file(s) are affected through the import chain")
    add("API exposure", min(15, len(routes) * 5),
        f"{len(routes)} API route(s) sit in or downstream of this file")
    if affected and not tests:
        add("No test coverage", 15,
            "other files depend on this one, but no test imports it, directly or indirectly")
    add("Change frequency", min(10, churn * 2),
        f"touched by {churn} of the analysed commits")
    hidden = [c for c in co_change if c["hidden_coupling"] and c["confidence"] >= 0.5]
    add("Hidden coupling", min(10, len(hidden) * 5),
        f"{len(hidden)} file(s) usually change with this one but have no import link")

    score = min(100, sum(f["points"] for f in factors))

    return {
        "file": path,
        "language": target.language,
        "kind": target.kind,
        "risk": {"score": score, "level": _level(score), "factors": factors},
        "direct_dependents": direct,
        "indirect_dependents": indirect,
        "affected_tests": tests,
        "affected_routes": routes,
        "depends_on": describe(dependencies),
        "co_change": co_change,
        "recent_commits": recent_commits,
        "history_commits_analysed": churn,
    }