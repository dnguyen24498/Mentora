from app.knowledge.models import DocumentMetadata, DocumentType
from app.knowledge.pipeline import IngestionPipeline
from app.presentation.models import SlideDeck
from app.presentation.parser import PresentationParser


class UploadService:
    """Handles course material uploads.

    Documents (text/markdown/pdf/pptx/docx) are ingested into the RAG index for
    later student question answering. A presentation file is read into a
    SlideDeck for teaching.
    """

    def __init__(
        self,
        ingestion: IngestionPipeline,
        presentation_parsers: dict[DocumentType, PresentationParser],
    ) -> None:
        self._ingestion = ingestion
        self._presentation_parsers = presentation_parsers

    def ingest_document(
        self,
        content: bytes,
        document_id: str,
        content_type: DocumentType,
        metadata: DocumentMetadata | None = None,
    ):
        return self._ingestion.ingest(content, document_id, content_type, metadata)

    def read_presentation(
        self,
        content: bytes,
        document_id: str,
        content_type: DocumentType,
        metadata: DocumentMetadata | None = None,
    ) -> SlideDeck:
        parser = self._presentation_parsers.get(content_type)
        if parser is None:
            raise ValueError(f"no presentation parser registered for content type {content_type!r}")
        return parser.parse(content, document_id, metadata)
