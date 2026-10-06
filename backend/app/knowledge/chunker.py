from app.knowledge.models import Chunk, DocumentMetadata, ParsedDocument


class TextChunker:
    """Splits cleaned text into overlapping chunks, preserving metadata."""

    def __init__(self, chunk_size: int = 800, overlap: int = 100) -> None:
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(self, document: ParsedDocument, metadata: DocumentMetadata | None = None) -> list[Chunk]:
        meta = metadata or DocumentMetadata()
        chunks: list[Chunk] = []
        for section in document.sections:
            section_meta = section.metadata.model_copy(update=meta.model_dump(exclude_none=True))
            for i, piece in enumerate(self._split(section.text)):
                chunk = Chunk(
                    chunk_id=f"{document.document_id}:{len(chunks)}",
                    text=piece,
                    metadata=section_meta.model_copy(update={"document_id": document.document_id}),
                )
                chunks.append(chunk)
        return chunks

    def _split(self, text: str) -> list[str]:
        if not text:
            return []
        words = text.split()
        if not words:
            return []
        pieces: list[str] = []
        start = 0
        while start < len(words):
            end = start + self._chunk_size
            pieces.append(" ".join(words[start:end]))
            if end >= len(words):
                break
            start = end - self._overlap
        return pieces
