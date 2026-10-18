#!/usr/bin/env python3
"""Local-stack mock TTS (V0-012).

``dev/README.md``: *"Local stack MUST include ... mock STT/TTS/LLM/SFU"*. This is
the mock TTS entry point: it drives the same deterministic neutral-voice adapter the
backend ships (``app/providers/deterministic.py``), so the dev stack and the tests
speak through one implementation and produce identical bytes.

It is stdlib-only and needs no installation beyond the repo:

    python3 dev/mocks/tts_mock.py --text "Hello class" --marker 0:start --out /tmp/tts.wav

Every chunk is a headerless PCM frame; concatenating them and writing the WAV header
once yields the utterance, which ``--out`` does for you. The printed JSON is the
outcome the classroom would observe (status, characters, chunks, duration, markers).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.providers.deterministic import wav_bytes  # noqa: E402
from app.providers.factory import build_speech_service  # noqa: E402
from app.speech.models import (  # noqa: E402
    MarkerPlan,
    SpeechMarker,
    SpeechRequest,
    normalize_text,
)


def _parse_marker(spec: str) -> SpeechMarker:
    """``INDEX:MARKER_ID`` (a marker id may be omitted)."""

    index, _, marker_id = spec.partition(":")
    try:
        text_index = int(index)
    except ValueError as exc:  # pragma: no cover - argument error
        raise argparse.ArgumentTypeError(f"marker index must be an integer: {spec!r}") from exc
    return SpeechMarker(marker_id=marker_id or f"m{text_index}", text_index=text_index)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic mock TTS for the local stack.")
    parser.add_argument(
        "--text",
        default="Hello from the Mentora neutral voice mock.",
        help="the utterance to synthesize",
    )
    parser.add_argument("--generation", type=int, default=1, help="idempotency key")
    parser.add_argument(
        "--marker",
        action="append",
        default=[],
        metavar="INDEX:MARKER_ID",
        help="a semantic marker on the normalized text (repeatable)",
    )
    parser.add_argument("--out", type=Path, default=None, help="write the utterance as a WAV here")
    parser.add_argument("--institution", default="local-dev", help="tenant id for telemetry")
    args = parser.parse_args(argv)

    text = normalize_text(args.text)
    markers = tuple(_parse_marker(spec) for spec in args.marker)

    service = build_speech_service()
    chunks = []
    outcome = service.speak(
        SpeechRequest(
            text=text,
            generation=args.generation,
            marker_plan=MarkerPlan(markers=markers),
            institution_id=args.institution,
        ),
        on_chunk=chunks.append,
    )

    summary: dict = {
        "provider": service.provider.identity().to_dict(),
        "generation": args.generation,
        "normalized_characters": len(text),
        "outcome": outcome.to_dict(),
        "chunks": [{"sequence": c.sequence, "byte_size": c.byte_size} for c in chunks],
    }

    if outcome.spoken and outcome.segment is not None:
        pcm = b"".join(chunk.audio for chunk in chunks)
        summary["audio_bytes"] = len(pcm)
        if args.out is not None:
            args.out.write_bytes(
                wav_bytes(
                    pcm,
                    sample_rate=outcome.segment.sample_rate,
                    bytes_per_sample=outcome.segment.bytes_per_sample,
                    channels=outcome.segment.channels,
                )
            )
            summary["wav"] = str(args.out)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
