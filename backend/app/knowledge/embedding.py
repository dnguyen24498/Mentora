import hashlib
import math

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Replaceable interface for a text-embedding model."""

    name: str

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic hash-based embeddings for tests and local development."""

    name = "fake-embedding"

    def __init__(self, dimensions: int = 128) -> None:
        self._dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        for token in text.lower().split():
            digest = hashlib.md5(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:
            return vector
        return [v / norm for v in vector]
