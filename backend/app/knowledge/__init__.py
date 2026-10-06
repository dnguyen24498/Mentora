from app.knowledge.chunker import TextChunker
from app.knowledge.cleaner import TextCleaner
from app.knowledge.embedding import EmbeddingProvider, FakeEmbeddingProvider
from app.knowledge.index import InMemoryVectorIndex, VectorIndex
from app.knowledge.models import (
    Chunk,
    DocumentMetadata,
    DocumentType,
    ParsedDocument,
    ParsedSection,
    ScoredChunk,
)
from app.knowledge.parser import (
    DocxDocumentParser,
    DocumentParser,
    MarkdownDocumentParser,
    PdfDocumentParser,
    PptxDocumentParser,
    TextDocumentParser,
)
from app.knowledge.pipeline import IngestionPipeline

DEFAULT_PARSERS: dict[DocumentType, DocumentParser] = {
    DocumentType.TEXT: TextDocumentParser(),
    DocumentType.MARKDOWN: MarkdownDocumentParser(),
    DocumentType.PDF: PdfDocumentParser(),
    DocumentType.PPTX: PptxDocumentParser(),
    DocumentType.DOCX: DocxDocumentParser(),
}

__all__ = [
    "DEFAULT_PARSERS",
    "DocxDocumentParser",
    "DocumentMetadata",
    "DocumentParser",
    "DocumentType",
    "EmbeddingProvider",
    "FakeEmbeddingProvider",
    "IngestionPipeline",
    "InMemoryVectorIndex",
    "MarkdownDocumentParser",
    "ParsedDocument",
    "ParsedSection",
    "PdfDocumentParser",
    "PptxDocumentParser",
    "ScoredChunk",
    "TextChunker",
    "TextCleaner",
    "TextDocumentParser",
    "VectorIndex",
]
