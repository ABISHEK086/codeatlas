import numpy as np
from fastembed import TextEmbedding

MODEL_NAME = "BAAI/bge-small-en-v1.5"  # 384 dims
_model: TextEmbedding | None = None


def get_model() -> TextEmbedding:
    """Loaded lazily: the first call downloads the model."""
    global _model
    if _model is None:
        _model = TextEmbedding(model_name=MODEL_NAME)
    return _model


def embed_documents(texts: list[str]) -> list[np.ndarray]:
    return list(get_model().embed(texts, batch_size=32))


def embed_query(text: str) -> np.ndarray:
    # bge models use a special query prefix, which query_embed adds for us
    return next(iter(get_model().query_embed(text)))