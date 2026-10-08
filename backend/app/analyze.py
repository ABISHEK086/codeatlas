import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import Edge, File, Symbol
from .parsing import make_parsers, parse_file
from .resolve import Resolver

log = logging.getLogger("codeatlas.analyze")


def analyze_repo(db: Session, repo_id: int) -> dict:
    files = db.execute(
        select(File.id, File.path, File.language, File.kind, File.content)
        .where(File.repo_id == repo_id)
    ).all()

    # clear previous analysis so this can be re-run safely
    db.execute(delete(Symbol).where(
        Symbol.file_id.in_(select(File.id).where(File.repo_id == repo_id))))
    db.execute(delete(Edge).where(Edge.repo_id == repo_id))

    paths = {f.path: f.id for f in files}
    resolver = Resolver(paths)
    parsers = make_parsers()

    symbol_count = 0
    parse_errors = 0
    edges: dict[tuple[int, int], str] = {}

    for f in files:
        if f.kind not in ("source", "test"):
            continue
        try:
            result = parse_file(parsers, f.path, f.language, f.content)
        except Exception:
            log.exception("parse failed for %s", f.path)
            parse_errors += 1
            continue
        if result is None:
            continue

        for s in result.symbols:
            db.add(Symbol(file_id=f.id, name=s.name, kind=s.kind,
                          start_line=s.start_line, end_line=s.end_line))
            symbol_count += 1

        for ref in result.imports:
            for target in resolver.resolve(f.path, f.language, ref):
                dst = paths[target]
                if dst != f.id:
                    edges[(f.id, dst)] = "tests" if f.kind == "test" else "imports"

    db.add_all(
        Edge(repo_id=repo_id, src_file_id=src, dst_file_id=dst, kind=kind)
        for (src, dst), kind in edges.items()
    )
    db.commit()
    return {"files_parsed": len(files), "symbols": symbol_count,
            "edges": len(edges), "parse_errors": parse_errors}