import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Edge, File


def build_graph(db: Session, repo_id: int) -> nx.DiGraph:
    """Edge A -> B means 'A depends on B' (A imports B)."""
    g = nx.DiGraph()
    for f in db.execute(
        select(File.id, File.path, File.kind, File.language).where(File.repo_id == repo_id)
    ):
        g.add_node(f.id, path=f.path, kind=f.kind, language=f.language)
    for e in db.execute(
        select(Edge.src_file_id, Edge.dst_file_id, Edge.kind).where(Edge.repo_id == repo_id)
    ):
        g.add_edge(e.src_file_id, e.dst_file_id, kind=e.kind)
    return g


def dependents(g: nx.DiGraph, file_id: int) -> dict[int, int]:
    """Everything that could break if file_id changes -> {file_id: distance}.
    Walks the edges backwards, so it also finds indirect dependents."""
    dist = nx.single_source_shortest_path_length(g.reverse(copy=False), file_id)
    dist.pop(file_id, None)
    return dist


def dependencies(g: nx.DiGraph, file_id: int) -> dict[int, int]:
    """Everything file_id relies on -> {file_id: distance}."""
    dist = nx.single_source_shortest_path_length(g, file_id)
    dist.pop(file_id, None)
    return dist