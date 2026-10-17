# Content Models, Fidelity, and Media

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define scenes, stable objects, reveal steps, and multimodal timelines.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Scene includes stable ID/source, normalized dimensions/bounds, fallback render, structured objects, notes, refs, fidelity, warnings, provenance, and steps. Stable object identity changes referenced by lessons require review.

## Fidelity classification

`fidelity` records **how** a scene's fallback render relates to its source, and every scene carries exactly one value:

| Value | Meaning |
| --- | --- |
| `NATIVE_RENDERED` | produced by a native/compatible engine (no such engine is accepted yet) |
| `COMPATIBLE_RENDERED` | produced by a compatible engine (no such engine is accepted yet) |
| `STRUCTURAL_RENDERED` | the source slide's own geometry and styling reproduced structurally |
| `THEMED_RENDERED` | the extracted *content* re-authored in the platform theme |
| `DEGRADED_RENDERED` | renderable, but a human check of meaning is required |

`THEMED_RENDERED` is deliberately **not** on the fidelity-to-source ladder: nothing is claimed about the original appearance, so consumers must not read it as "better" or "worse" than `STRUCTURAL_RENDERED`. It is still an explicit, non-native classification, never a native render. A failed render is a `FAILED` *status*, not a fidelity, and blocks publication.

Instructional animations become visibility/semantic steps; decorative effects may be dropped. Video becomes timestamped ASR, scene-change frames, OCR, visual events, and segments that runtime can play/pause/resume exactly.

## Locked Decisions Implemented

- `DEC-CONTENT-006`
- `DEC-CONTENT-007`
