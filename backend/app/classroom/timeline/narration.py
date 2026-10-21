"""Build one scene's narration from the package the session pinned (V0-013).

The classroom never narates a draft revision or a newer publication: the script is
read from the pinned package's lesson plan (``DEC-CONTENT-005``), in this fixed
precedence order:

1. the section's authored ``script``;
2. its authored ``fallback_script``;
3. the scene's speaker notes;
4. the slide's own text.

Nothing is generated, re-ordered or dropped. A scene with no authored text yields
an empty script, and the timeline reports that explicitly rather than inventing
words.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from app.classroom.scene_source import PinnedSceneSummary
from app.classroom.timeline.chunking import (
    DEFAULT_MAX_CHUNK_CHARACTERS,
    DEFAULT_MIN_CHUNK_CHARACTERS,
    chunks_for,
)
from app.classroom.timeline.models import (
    NarrationScript,
    NarrationSource,
)
from app.speech.models import DEFAULT_LANGUAGE, NEUTRAL_VOICE_ID, normalize_text


def _authored(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def section_for(
    lesson_plan: Mapping[str, Any], scene_id: str, order: int
) -> Mapping[str, Any]:
    """The pinned section that introduces ``scene_id``.

    A plan may revisit a scene. The closest section to the slide's own position is
    the deterministic choice, matching the navigation resolver in
    :meth:`ClassroomService.navigate_to_order`.
    """

    sections = [
        section
        for section in (lesson_plan.get("sections") or [])
        if isinstance(section, dict)
    ]
    matches = [
        (index, section)
        for index, section in enumerate(sections)
        if section.get("scene_id") == scene_id
    ]
    if not matches:
        return {}
    _, section = min(matches, key=lambda item: abs(item[0] - order))
    return section


def narration_text(scene: PinnedSceneSummary, section: Mapping[str, Any]) -> tuple[str, NarrationSource]:
    """The authored text for one scene and the source it came from."""

    script = _authored(section.get("script"))
    if script:
        return script, NarrationSource.LESSON_SCRIPT

    fallback = _authored(section.get("fallback_script"))
    if fallback:
        return fallback, NarrationSource.FALLBACK_SCRIPT

    notes = _authored(scene.notes)
    if notes:
        return notes, NarrationSource.SPEAKER_NOTES

    slide_text = "\n".join(
        line.strip() for line in scene.text if line and line.strip()
    )
    if slide_text:
        return slide_text, NarrationSource.SLIDE_TEXT

    return "", NarrationSource.NONE


def build_narration(
    *,
    scene: PinnedSceneSummary,
    lesson_plan: Mapping[str, Any],
    order: Optional[int] = None,
    voice_id: str = NEUTRAL_VOICE_ID,
    language: str = DEFAULT_LANGUAGE,
    max_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS,
    min_characters: int = DEFAULT_MIN_CHUNK_CHARACTERS,
) -> NarrationScript:
    """Build the semantic narration for one pinned scene."""

    scene_order = scene.order if order is None else int(order)
    section = section_for(lesson_plan, scene.scene_id, scene_order)
    text, source = narration_text(scene, section)
    normalized = normalize_text(text)
    markers = tuple(
        str(marker) for marker in (section.get("safe_markers") or []) if str(marker)
    )
    chunks = chunks_for(
        normalized,
        marker_ids=markers,
        max_characters=max_characters,
        min_characters=min_characters,
    )
    return NarrationScript(
        scene_id=scene.scene_id,
        order=scene_order,
        source=source,
        text=normalized,
        chunks=chunks,
        voice_id=voice_id,
        language=language,
    )


__all__ = ["build_narration", "narration_text", "section_for"]
