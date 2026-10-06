from abc import ABC, abstractmethod

from app.knowledge.models import DocumentMetadata, DocumentType
from app.presentation.models import Slide, SlideDeck


class PresentationParser(ABC):
    """Replaceable interface for reading a presentation file into a SlideDeck."""

    content_type: DocumentType

    @abstractmethod
    def parse(self, content: bytes, document_id: str, metadata: DocumentMetadata | None = None) -> SlideDeck:
        ...


class MarkdownPresentationParser(PresentationParser):
    """Treats a Markdown file as a slide deck.

    Slides are separated by ``---`` on its own line; the first heading in each
    slide becomes the title and the rest the content.
    """

    content_type = DocumentType.MARKDOWN

    def parse(self, content: bytes, document_id: str, metadata: DocumentMetadata | None = None) -> SlideDeck:
        meta = metadata or DocumentMetadata()
        text = content.decode("utf-8", errors="replace")
        slides: list[Slide] = []
        for raw in self._split_slides(text):
            title, body = self._split_title(raw)
            slides.append(
                Slide(
                    index=len(slides) + 1,
                    title=title,
                    content=body,
                    metadata=meta,
                )
            )
        return SlideDeck(document_id=document_id, slides=slides)

    @staticmethod
    def _split_slides(text: str) -> list[str]:
        parts = [p.strip() for p in text.split("\n---\n")]
        return [p for p in parts if p]

    @staticmethod
    def _split_title(raw: str) -> tuple[str, str]:
        lines = raw.splitlines()
        if lines and lines[0].startswith("#"):
            title = lines[0].lstrip("#").strip()
            body = "\n".join(lines[1:]).strip()
            return title, body
        return "", raw


class PdfPresentationParser(PresentationParser):
    """Stub: real PDF slide extraction is wired in later behind this interface."""

    content_type = DocumentType.PDF

    def parse(self, content: bytes, document_id: str, metadata: DocumentMetadata | None = None) -> SlideDeck:
        raise NotImplementedError("PDF presentation parsing requires a real extractor; not wired yet")


class PptxPresentationParser(PresentationParser):
    """Stub: real PPTX slide extraction is wired in later behind this interface."""

    content_type = DocumentType.PPTX

    def parse(self, content: bytes, document_id: str, metadata: DocumentMetadata | None = None) -> SlideDeck:
        raise NotImplementedError("PPTX presentation parsing requires a real extractor; not wired yet")
