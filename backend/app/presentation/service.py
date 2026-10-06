from collections.abc import AsyncIterator

from app.presentation.models import PresentationAction, PresentationEvent


class PresentationService:
    """Builds and emits semantic presentation events for the Web Classroom."""

    def emit(self, action: PresentationAction, **payload) -> PresentationEvent:
        return PresentationEvent(action=action, payload=payload)

    def goto_slide(self, slide: int) -> PresentationEvent:
        return self.emit(PresentationAction.GOTO_SLIDE, slide=slide)

    def highlight(self, target: str) -> PresentationEvent:
        return self.emit(PresentationAction.HIGHLIGHT, target=target)

    def show_diagram(self, diagram_id: str) -> PresentationEvent:
        return self.emit(PresentationAction.SHOW_DIAGRAM, diagram_id=diagram_id)

    def show_equation(self, equation: str) -> PresentationEvent:
        return self.emit(PresentationAction.SHOW_EQUATION, equation=equation)

    def show_code(self, code: str, language: str = "python") -> PresentationEvent:
        return self.emit(PresentationAction.SHOW_CODE, code=code, language=language)

    def start_quiz(self, quiz_id: str) -> PresentationEvent:
        return self.emit(PresentationAction.START_QUIZ, quiz_id=quiz_id)

    async def replay(self, events: list[PresentationEvent]) -> AsyncIterator[PresentationEvent]:
        for event in events:
            yield event
