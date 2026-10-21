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
current slide as a new generation. Students see the slide with no transcript by
default (a collapsed accessibility disclosure keeps the text available) and do not
hear audio until the SFU path (V1-005, `DEC-TECH-004` `OPEN`).
