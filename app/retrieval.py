from __future__ import annotations

import re
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import TOP_K


class EmbeddingService:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 384), dtype=float)
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return np.array(vectors, dtype=float)


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z0-9]+", text.lower()) if len(t) >= 2}


def cosine_search(
    query_embedding: np.ndarray,
    candidates: list[dict[str, Any]],
    query_text: str,
    top_k: int = TOP_K,
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    matrix = np.array([row["embedding"] for row in candidates], dtype=float)
    if matrix.ndim != 2:
        return []

    semantic_scores = matrix @ query_embedding
    q_tokens = _tokenize(query_text)

    blended_scores: list[float] = []
    for i, row in enumerate(candidates):
        text_tokens = _tokenize(row.get("text", ""))
        overlap = len(q_tokens.intersection(text_tokens))
        lexical = overlap / max(1, len(q_tokens))
        blended = (0.8 * float(semantic_scores[i])) + (0.2 * lexical)
        blended_scores.append(blended)

    blended_np = np.array(blended_scores, dtype=float)
    top_indices = np.argsort(blended_np)[::-1][:top_k]

    results: list[dict[str, Any]] = []
    for idx in top_indices:
        row = dict(candidates[int(idx)])
        row["score"] = float(blended_np[int(idx)])
        results.append(row)
    return results


def retrieve_relevant_chunks(
    query: str,
    candidates: list[dict[str, Any]],
    embedder: EmbeddingService,
    top_k: int = TOP_K,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    query_embedding = embedder.embed([query])[0]
    return cosine_search(query_embedding=query_embedding, candidates=candidates, query_text=query, top_k=top_k)
