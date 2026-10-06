from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.knowledge.models import DocumentMetadata


class Slide(BaseModel):
    index: int
    title: str = ""
    content: str = ""
    notes: str = ""
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)


class SlideDeck(BaseModel):
    document_id: str
    slides: list[Slide] = Field(default_factory=list)


class PresentationAction(str, Enum):
    GOTO_SLIDE = "goto_slide"
    NEXT_SLIDE = "next_slide"
    PREVIOUS_SLIDE = "previous_slide"
    HIGHLIGHT = "highlight"
    SHOW_DIAGRAM = "show_diagram"
    SHOW_EQUATION = "show_equation"
    SHOW_CODE = "show_code"
    SHOW_IMAGE = "show_image"
    START_ANIMATION = "start_animation"
    START_QUIZ = "start_quiz"
    PAUSE = "pause"
    RESUME = "resume"


class PresentationEvent(BaseModel):
    """Semantic presentation command sent over the control channel.

    These are structured events, never LLM-generated HTML.
    """

    type: Literal["presentation.action"] = "presentation.action"
    action: PresentationAction
    payload: dict = {}
