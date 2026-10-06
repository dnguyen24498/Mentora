import re

from app.knowledge.models import ParsedDocument, ParsedSection


class TextCleaner:
    """Normalizes extracted text before chunking."""

    def clean(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" +", " ", text)
        return text.strip()

    def clean_document(self, document: ParsedDocument) -> ParsedDocument:
        sections = [
            ParsedSection(text=self.clean(section.text), metadata=section.metadata)
            for section in document.sections
        ]
        return document.model_copy(update={"sections": sections})
