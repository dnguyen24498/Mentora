from enum import Enum

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    PDF = "pdf"
    PPTX = "pptx"
    DOCX = "docx"
    MARKDOWN = "markdown"
    TEXT = "text"


class DocumentMetadata(BaseModel):
    course_id: str | None = None
    chapter_id: str | None = None
    lesson_id: str | None = None
    section: str | None = None
    slide_number: int | None = None
    page_number: int | None = None
    document_id: str | None = None
    content_type: str | None = None
    access_scope: str = "course"


class ParsedSection(BaseModel):
    text: str
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)


class ParsedDocument(BaseModel):
    document_id: str
    content_type: DocumentType
    sections: list[ParsedSection] = Field(default_factory=list)


class Chunk(BaseModel):
    chunk_id: str
    text: str
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    embedding: list[float] | None = None


class ScoredChunk(BaseModel):
    chunk: Chunk
    score: float
