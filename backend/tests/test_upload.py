import pytest

from app.knowledge import (
    DEFAULT_PARSERS,
    DocumentMetadata,
    DocumentType,
    FakeEmbeddingProvider,
    IngestionPipeline,
    InMemoryVectorIndex,
    TextChunker,
    TextCleaner,
)
from app.presentation import MarkdownPresentationParser, PresentationParser
from app.upload import UploadService

PRESENTATION_PARSERS: dict[DocumentType, PresentationParser] = {
    DocumentType.MARKDOWN: MarkdownPresentationParser(),
}


@pytest.fixture
def upload() -> UploadService:
    pipeline = IngestionPipeline(
        parsers=DEFAULT_PARSERS,
        cleaner=TextCleaner(),
        chunker=TextChunker(chunk_size=100, overlap=10),
        embedder=FakeEmbeddingProvider(),
        index=InMemoryVectorIndex(),
    )
    return UploadService(ingestion=pipeline, presentation_parsers=PRESENTATION_PARSERS)


def test_read_markdown_presentation(upload: UploadService) -> None:
    content = b"# Intro\nWelcome\n---\n# Body\nDetails here\n---\n# End\nThanks"
    deck = upload.read_presentation(content, "deck1", DocumentType.MARKDOWN)
    assert deck.document_id == "deck1"
    assert len(deck.slides) == 3
    assert deck.slides[0].title == "Intro"
    assert deck.slides[0].content == "Welcome"
    assert deck.slides[1].title == "Body"


def test_read_presentation_missing_parser(upload: UploadService) -> None:
    with pytest.raises(ValueError):
        upload.read_presentation(b"x", "deck1", DocumentType.PPTX)


def test_ingest_document_flows_into_index(upload: UploadService) -> None:
    metadata = DocumentMetadata(course_id="c1", section="lesson-1")
    chunks = upload.ingest_document(b"Cells are the basic unit of life.", "doc1", DocumentType.TEXT, metadata)
    assert chunks
    assert chunks[0].metadata.course_id == "c1"


def test_document_and_presentation_are_independent(upload: UploadService) -> None:
    upload.ingest_document(b"mitochondria produces ATP", "doc1", DocumentType.TEXT)
    deck = upload.read_presentation(b"# Slide\nOnly", "deck1", DocumentType.MARKDOWN)
    assert len(deck.slides) == 1
