import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .chunking import chunk_file
from .embeddings import embed_documents, embed_query
from .models import Chunk, File, Symbol
from .vectors import to_blob, top_k

log = logging.getLogger("codeatlas.indexer")

INDEXED_KINDS = ("source", "test", "doc")
BATCH = 64


def index_repo(db: Session, repo_id: int) -> dict:
    db.execute(delete(Chunk).where(Chunk.repo_id == repo_id))
    db.commit()

    files = db.execute(
        select(File.id, File.path, File.content)
        .where(File.repo_id == repo_id, File.kind.in_(INDEXED_KINDS))
    ).all()

    pending: list[tuple[int, str, object]] = []   # (file_id, path, ChunkSpan)
    for f in files:
        syms = db.execute(
            select(Symbol.start_line, Symbol.end_line).where(Symbol.file_id == f.id)
        ).all()
        for span in chunk_file(f.content, [(s.start_line, s.end_line) for s in syms]):
            pending.append((f.id, f.path, span))

    total = 0
    for i in range(0, len(pending), BATCH):
        batch = pending[i:i + BATCH]
        # prefix with the path so "auth router" style queries match file names too
        vectors = embed_documents([f"{path}\n{span.content}" for _, path, span in batch])
        db.add_all(
            Chunk(
                repo_id=repo_id, file_id=file_id,
                start_line=span.start_line, end_line=span.end_line,
                content=span.content, embedding=to_blob(vec),
            )
            for (file_id, _path, span), vec in zip(batch, vectors)
        )
        db.commit()
        total += len(batch)

    return {"files_indexed": len(files), "chunks": total}


def search_repo(db: Session, repo_id: int, query: str, k: int = 5,
                kind: str | None = None) -> list[dict]:
    q = select(Chunk.id, Chunk.embedding).where(
        Chunk.repo_id == repo_id, Chunk.embedding.is_not(None))
    if kind:
        q = q.join(File, File.id == Chunk.file_id).where(File.kind == kind)
    rows = db.execute(q).all()
    if not rows:
        return []

    hits = top_k(embed_query(query), [r.embedding for r in rows], k)
    scores = {rows[i].id: s for i, s in hits}

    found = db.execute(
        select(Chunk.id, Chunk.start_line, Chunk.end_line, Chunk.content, File.path, File.kind)
        .join(File, File.id == Chunk.file_id)
        .where(Chunk.id.in_(scores))
    ).all()
    results = [{
        "chunk_id": c.id, "path": c.path, "kind": c.kind,
        "start_line": c.start_line, "end_line": c.end_line,
        "score": round(scores[c.id], 4), "content": c.content,
    } for c in found]
    return sorted(results, key=lambda r: -r["score"])