"""Word-safe semantic chunking for narration (V0-013).

A provider that is asked for a whole slide in one request has a long
time-to-first-audio: the first word is not heard until the last word is
synthesized. The timeline therefore cuts the authored script into **semantic**
chunks before it calls the provider. The rules are deliberately simple and
deterministic:

* split on whitespace, never inside a word;
* close a chunk at a sentence-ending punctuation mark once it is long enough to be
  useful, and otherwise at the configured character budget;
* keep the character offsets into the normalized script so a marker or a caption
  can be mapped back to the authored text.

A single pathological token longer than the budget is kept whole (the provider's
own input bound still applies). Splitting a URL or a chemical name in the middle
would be worse than an oversized chunk.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from app.classroom.timeline.models import TextChunk
from app.speech.models import normalize_text

_WORD = re.compile(r"\S+")
_SENTENCE_END = (".", "!", "?", ";", ":")

#: A chunk shorter than this is combined with the next one when no sentence
#: boundary forces a cut, so the provider is not called for a two-word fragment.
DEFAULT_MIN_CHUNK_CHARACTERS = 40
#: The soft upper bound. A sentence may close before it; a long sentence is cut at
#: the last word boundary at or before it.
DEFAULT_MAX_CHUNK_CHARACTERS = 160


def _close(
    text: str, words: list[tuple[int, int]], *, index: int
) -> TextChunk:
    start = words[0][0]
    end = words[-1][1]
    return TextChunk(index=index, text=text[start:end], char_start=start, char_end=end)


def split_text(
    text: str,
    *,
    max_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS,
    min_characters: int = DEFAULT_MIN_CHUNK_CHARACTERS,
) -> tuple[TextChunk, ...]:
    """Cut normalized ``text`` into word-safe chunks.

    The output is contiguous: ``chunks[n].char_end == chunks[n + 1].char_start`` is
    not guaranteed when whitespace was collapsed, but each ``char_start``/``char_end``
    indexes the same normalized string and slicing it yields the chunk text.
    """

    normalized = normalize_text(text)
    if not normalized:
        return ()

    budget = max(1, int(max_characters))
    floor = max(1, min(int(min_characters), budget))
    words = [(match.start(), match.end()) for match in _WORD.finditer(normalized)]
    if not words:
        return ()

    chunks: list[TextChunk] = []
    current: list[tuple[int, int]] = []

    def close() -> None:
        nonlocal current
        if current:
            chunks.append(_close(normalized, current, index=len(chunks)))
            current = []

    for start, end in words:
        if current:
            current_start = current[0][0]
            # Close before this word would push the chunk past the budget. A
            # single word is never split: if it alone exceeds the budget it still
            # starts (and closes) its own chunk.
            if end - current_start > budget:
                close()
        current.append((start, end))
        current_end = current[-1][1]
        current_length = current_end - current[0][0]
        word = normalized[start:end]
        if (
            word.endswith(_SENTENCE_END)
            and current_length >= floor
        ):
            close()

    close()
    return tuple(chunks)


def assign_markers(
    chunks: tuple[TextChunk, ...],
    marker_ids: Iterable[str],
) -> tuple[TextChunk, ...]:
    """Attach safe markers to chunks, in their authored order.

    A safe marker names a reveal step, not a word. The deterministic mapping is
    one marker per chunk in order; extra markers (more markers than chunks) land on
    the last chunk, and extra chunks simply have no marker. A marker is never
    duplicated, so the provider's marker plan remains valid.
    """

    ordered = tuple(dict.fromkeys(str(marker) for marker in marker_ids if str(marker)))
    if not ordered or not chunks:
        return chunks
    assigned: dict[int, list[str]] = {}
    for position, marker_id in enumerate(ordered):
        index = min(position, len(chunks) - 1)
        assigned.setdefault(index, []).append(marker_id)
    return tuple(
        TextChunk(
            index=chunk.index,
            text=chunk.text,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            marker_ids=tuple(assigned.get(chunk.index, chunk.marker_ids)),
        )
        for chunk in chunks
    )


def chunks_for(
    text: str,
    *,
    marker_ids: Iterable[str] = (),
    max_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS,
    min_characters: int = DEFAULT_MIN_CHUNK_CHARACTERS,
) -> tuple[TextChunk, ...]:
    """Split and attach markers in one call (the public convenience path)."""

    return assign_markers(
        split_text(
            text,
            max_characters=max_characters,
            min_characters=min_characters,
        ),
        marker_ids,
    )


__all__ = [
    "DEFAULT_MAX_CHUNK_CHARACTERS",
    "DEFAULT_MIN_CHUNK_CHARACTERS",
    "assign_markers",
    "chunks_for",
    "split_text",
]
