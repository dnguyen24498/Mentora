# Timeline, Presentation, and Resume

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Coordinate speech, visuals, cancellation, and semantic continuation.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Use marker priority: native TTS marker, forced alignment, audio PTS, estimated offset, segment fallback. Presentation events include deadline policy and target version. Client ignores duplicate/stale generations/events and reports sequence gaps.

Audio cancellation names cancel-through generation; client stops/clears/discards/ACKs. Checkpoint precedes student invitation. Resume validates versions/checkpoint, restores presentation, generates bridge phrase, and starts new segment/generation.

## Locked Decisions Implemented

- `DEC-RUNTIME-005`
- `DEC-RUNTIME-006`
- `DEC-TURN-007`

## Implemented narration (V0-013)

The teacher's stage narrates each pinned slide while auto-playing: pinned script →
word-safe chunks → provider-neutral voice → one WAV per chunk, played in order as it
arrives, and the slide advances when its narration has been heard. Speech failure
shows the authored text and paces the slide by its length (`DEC-TURN-009`). A slide
change, pause or end aborts the stream and cancels synthesis; Play restarts the
current slide as a new generation.

An enrolled student's page attaches to the teacher's **live generation** through an
in-process relay (`GET /classes/{classId}/narration`): it starts no synthesis and
copies the same WAV chunks, so a class does not pay one provider call per learner.
The relay is a V1-005 bridge, not the media plane — it is single-process and
best-effort, returns `204` while there is no current generation (the page retries),
ends at each generation's terminal verdict, and sends attached students a
cancellation if the teacher pauses or moves. The current slide is the unit of
replay: a late joiner receives the buffered chunks from that slide's start, so the
fast local mock — which can synthesize a whole slide before the student's next
attach — does not leave the class in silence, and the teacher's next slide
supersedes it. A completed generation stays replayable for a short TTL; the page
passes `after_generation` so waiting for the next slide does not replay the one it
just heard, and `expected_scene_id` keeps the audio under the slide the
authoritative snapshot shows. A student joining mid-slide is therefore aligned with
the displayed slide but may be a few seconds behind the teacher's own playout.
`DEC-TECH-004` remains `OPEN`; a multi-worker deployment needs the ordered/shared
path that decision will choose, not this in-memory relay.
Students see the slide with no transcript by default (a collapsed accessibility
disclosure keeps the text available) and can enable sound if the browser blocks
autoplay.
