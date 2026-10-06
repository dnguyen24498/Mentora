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


@pytest.fixture
def pipeline() -> IngestionPipeline:
    return IngestionPipeline(
        parsers=DEFAULT_PARSERS,
        cleaner=TextCleaner(),
        chunker=TextChunker(chunk_size=50, overlap=5),
        embedder=FakeEmbeddingProvider(dimensions=64),
        index=InMemoryVectorIndex(),
    )


def test_parse_text_document() -> None:
    parsed = DEFAULT_PARSERS[DocumentType.TEXT].parse(b"hello world", "doc1")
    assert parsed.content_type == DocumentType.TEXT
    assert parsed.sections[0].text == "hello world"


def test_parse_markdown_splits_on_headers() -> None:
    content = b"# Intro\nsome text\n# Body\nmore text"
    parsed = DEFAULT_PARSERS[DocumentType.MARKDOWN].parse(content, "doc1")
    assert len(parsed.sections) == 2
    assert parsed.sections[0].text.startswith("# Intro")


def test_cleaner_normalizes_whitespace() -> None:
    cleaner = TextCleaner()
    assert cleaner.clean("a   b\n\n\n\nc\r\nd") == "a b\n\nc\nd"


def test_chunker_overlaps_and_respects_size() -> None:
    chunker = TextChunker(chunk_size=10, overlap=3)
    words = "one two three four five six seven eight nine ten"
    pieces = chunker._split(words)
    assert pieces
    assert all(len(p.split()) <= 10 for p in pieces)


def test_ingest_embeds_and_indexes(pipeline: IngestionPipeline) -> None:
    content = b"The mitochondria is the powerhouse of the cell."
    metadata = DocumentMetadata(course_id="bio101", section="cell-biology")
    chunks = pipeline.ingest(content, "doc1", DocumentType.TEXT, metadata)
    assert chunks
    assert chunks[0].embedding is not None
    assert chunks[0].metadata.course_id == "bio101"
    assert chunks[0].metadata.document_id == "doc1"


def test_search_returns_relevant_chunks(pipeline: IngestionPipeline) -> None:
    pipeline.ingest(b"photosynthesis converts sunlight into energy", "doc1", DocumentType.TEXT)
    pipeline.ingest(b"the history of the roman empire", "doc2", DocumentType.TEXT)
    results = pipeline.search("how do plants make energy", top_k=1)
    assert results
    assert results[0].score > 0.0


def test_missing_parser_raises(pipeline: IngestionPipeline) -> None:
    parsers = {DocumentType.TEXT: DEFAULT_PARSERS[DocumentType.TEXT]}
    pipeline._parsers = parsers
    with pytest.raises(ValueError):
        pipeline.parse(b"x", "doc1", DocumentType.PDF)
