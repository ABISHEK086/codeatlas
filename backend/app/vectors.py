import numpy as np


def to_blob(vec) -> bytes:
    """Normalize and store as float32 bytes. Normalized vectors make
    cosine similarity a plain dot product."""
    v = np.asarray(vec, dtype=np.float32)
    n = np.linalg.norm(v)
    return (v / n if n else v).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def top_k(query_vec, blobs: list[bytes], k: int = 5) -> list[tuple[int, float]]:
    """Return [(index, score)] for the k most similar blobs."""
    if not blobs:
        return []
    matrix = np.vstack([from_blob(b) for b in blobs])      # (N, dim)
    q = np.asarray(query_vec, dtype=np.float32)
    q = q / (np.linalg.norm(q) or 1.0)
    scores = matrix @ q
    k = min(k, len(scores))
    idx = np.argpartition(-scores, k - 1)[:k]
    idx = idx[np.argsort(-scores[idx])]
    return [(int(i), float(scores[i])) for i in idx]