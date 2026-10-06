from app.knowledge.chunker import TextChunker
from app.knowledge.cleaner import TextCleaner
from app.knowledge.embedding import EmbeddingProvider
from app.knowledge.index import VectorIndex
from app.knowledge.models import (
    Chunk,
    DocumentMetadata,
    DocumentType,
    ParsedDocument,
    ScoredChunk,
)
from app.knowledge.parser import DocumentParser


class IngestionPipeline:
    """Runs the ingestion flow: parse -> clean -> chunk -> embed -> index."""

    def __init__(
        self,
        parsers: dict[DocumentType, DocumentParser],
        cleaner: TextCleaner,
        chunker: TextChunker,
        embedder: EmbeddingProvider,
        index: VectorIndex,
    ) -> None:
        self._parsers = parsers
        self._cleaner = cleaner
        self._chunker = chunker
        self._embedder = embedder
        self._index = index

    def parse(self, content: bytes, document_id: str, content_type: DocumentType, metadata: DocumentMetadata | None = None) -> ParsedDocument:
        parser = self._parsers.get(content_type)
        if parser is None:
            raise ValueError(f"no parser registered for content type {content_type!r}")
        return parser.parse(content, document_id, metadata)

    def ingest(
        self,
        content: bytes,
        document_id: str,
        content_type: DocumentType,
        metadata: DocumentMetadata | None = None,
    ) -> list[Chunk]:
        parsed = self.parse(content, document_id, content_type, metadata)
        cleaned = self._cleaner.clean_document(parsed)
        chunks = self._chunker.chunk(cleaned, metadata)
        for chunk in chunks:
            chunk.embedding = self._embedder.embed(chunk.text)
            self._index.upsert(chunk)
        return chunks

    def search(self, query: str, top_k: int = 5) -> list[ScoredChunk]:
        query_embedding = self._embedder.embed(query)
        return self._index.search(query_embedding, top_k)
