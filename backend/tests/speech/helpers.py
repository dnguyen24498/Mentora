"""Shared helpers for the speech contract/service tests (V0-012)."""

from __future__ import annotations

from app.speech.models import MarkerPlan, SpeechMarker, normalize_text

#: A deterministic utterance with stable character positions, so a marker plan is
#: reproducible across tests.
UTTERANCE = normalize_text(
    "  One two three four five six seven eight nine ten eleven twelve.  "
)

#: Markers at the start, mid-text and at the very end (the end marker exercises the
#: clamp onto the last chunk).
MARKERS = MarkerPlan(
    markers=(
        SpeechMarker("start", 0, "start"),
        SpeechMarker("middle", UTTERANCE.index("seven"), "beat"),
        SpeechMarker("end", len(UTTERANCE), "end"),
    )
)


class FakeClock:
    """A deterministic monotonic clock for deadline tests."""

    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def advance_to(self, seconds: float) -> None:
        self.now = seconds
