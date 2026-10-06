import math

from abc import ABC, abstractmethod

from app.knowledge.models import Chunk, ScoredChunk


class VectorIndex(ABC):
    """Replaceable interface for a vector/search index."""

    @abstractmethod
    def upsert(self, chunk: Chunk) -> None:
        ...

    @abstractmethod
    def search(self, query_embedding: list[float], top_k: int = 5) -> list[ScoredChunk]:
        ...


class InMemoryVectorIndex(VectorIndex):
    """Cosine-similarity index held in memory; used for tests and local dev."""

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []

    def upsert(self, chunk: Chunk) -> None:
        if chunk.embedding is None:
            raise ValueError("chunk must have an embedding before upsert")
        self._chunks.append(chunk)

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[ScoredChunk]:
        scored = [
            ScoredChunk(chunk=chunk, score=self._cosine(query_embedding, chunk.embedding or []))
            for chunk in self._chunks
        ]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:top_k]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)
