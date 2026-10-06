import pytest

from app.presentation import PresentationAction, PresentationService


def test_goto_slide_event() -> None:
    service = PresentationService()
    event = service.goto_slide(17)
    assert event.type == "presentation.action"
    assert event.action == PresentationAction.GOTO_SLIDE
    assert event.payload == {"slide": 17}


def test_highlight_event() -> None:
    service = PresentationService()
    event = service.highlight("query_vector")
    assert event.action == PresentationAction.HIGHLIGHT
    assert event.payload["target"] == "query_vector"


async def test_replay_yields_events_in_order() -> None:
    service = PresentationService()
    events = [service.goto_slide(1), service.highlight("x"), service.goto_slide(2)]
    replayed = [e async for e in service.replay(events)]
    assert replayed == events
