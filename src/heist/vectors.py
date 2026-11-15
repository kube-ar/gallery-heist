"""A small vector index, for the fast path.

    index = VectorIndex(["At 22:04 Mara Vos badged into the Map Room", ...])
    index.search("Who was in the east wing?", k=10)   # -> list of row numbers, best first

It embeds with a small static model (model2vec, no GPU, ~30 MB, downloaded on first use) and
ranks by cosine similarity. The deep path: write the cosine ranking yourself with numpy.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

MODEL = "minishlab/potion-base-8M"


@lru_cache(maxsize=1)
def _model():
    from model2vec import StaticModel

    return StaticModel.from_pretrained(MODEL)


def embed(texts: list[str]) -> np.ndarray:
    """One unit-length vector per text."""
    vectors = np.asarray(_model().encode(texts), dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-9)


class VectorIndex:
    def __init__(self, texts: list[str]):
        self.texts = list(texts)
        self.vectors = embed(self.texts) if self.texts else np.zeros((0, 1), dtype=np.float32)

    def search(self, query: str, k: int = 10) -> list[int]:
        if not self.texts:
            return []
        scores = self.vectors @ embed([query])[0]
        order = np.argsort(-scores, kind="stable")
        return [int(i) for i in order[:k]]
