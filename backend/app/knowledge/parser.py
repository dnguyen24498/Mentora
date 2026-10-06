from abc import ABC, abstractmethod

from app.knowledge.models import (
    DocumentMetadata,
    DocumentType,
    ParsedDocument,
    ParsedSection,
)


class DocumentParser(ABC):
    """Replaceable interface for extracting text from a source format."""

    content_type: DocumentType

    @abstractmethod
    def parse(
        self,
        content: bytes,
        document_id: str,
        metadata: DocumentMetadata | None = None,
    ) -> ParsedDocument:
        ...


class TextDocumentParser(DocumentParser):
    content_type = DocumentType.TEXT

    def parse(self, content: bytes, document_id: str, metadata: DocumentMetadata | None = None) -> ParsedDocument:
        meta = metadata or DocumentMetadata()
        return ParsedDocument(
            document_id=document_id,
            content_type=self.content_type,
            sections=[ParsedSection(text=content.decode("utf-8", errors="replace"), metadata=meta)],
        )


class MarkdownDocumentParser(DocumentParser):
    content_type = DocumentType.MARKDOWN

    def parse(self, content: bytes, document_id: str, metadata: DocumentMetadata | None = None) -> ParsedDocument:
        meta = metadata or DocumentMetadata()
        text = content.decode("utf-8", errors="replace")
        sections = self._split_headers(text)
        return ParsedDocument(
            document_id=document_id,
            content_type=self.content_type,
            sections=[ParsedSection(text=s, metadata=meta) for s in sections],
        )

    @staticmethod
    def _split_headers(text: str) -> list[str]:
        lines = text.splitlines()
        sections: list[str] = []
        current: list[str] = []
        for line in lines:
            if line.startswith("#"):
                if current:
                    sections.append("\n".join(current).strip())
                current = [line]
            else:
                current.append(line)
        if current:
            sections.append("\n".join(current).strip())
        return [s for s in sections if s]


class PdfDocumentParser(DocumentParser):
    """Stub: real PDF extraction is wired in later behind this interface."""

    content_type = DocumentType.PDF

    def parse(self, content: bytes, document_id: str, metadata: DocumentMetadata | None = None) -> ParsedDocument:
        raise NotImplementedError("PDF parsing requires a real extractor; not wired yet")


class PptxDocumentParser(DocumentParser):
    content_type = DocumentType.PPTX

    def parse(self, content: bytes, document_id: str, metadata: DocumentMetadata | None = None) -> ParsedDocument:
        raise NotImplementedError("PPTX parsing requires a real extractor; not wired yet")


class DocxDocumentParser(DocumentParser):
    content_type = DocumentType.DOCX

    def parse(self, content: bytes, document_id: str, metadata: DocumentMetadata | None = None) -> ParsedDocument:
        raise NotImplementedError("DOCX parsing requires a real extractor; not wired yet")
