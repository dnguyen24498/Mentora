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

Scene includes stable ID/source, normalized dimensions/bounds, fallback render, structured objects, notes, refs, fidelity, warnings, provenance, and steps. Stable object identity changes referenced by lessons require review. A scene also carries the art it **inherits** from its layout and master (`inherited_objects`, V0-019 v7): the deck's shared chrome, painted beneath its own objects and outside its reading order, text and object count.

## Fidelity classification

`fidelity` records **how** a scene's fallback render relates to its source, and every scene carries exactly one value:

| Value | Meaning |
| --- | --- |
| `NATIVE_RENDERED` | produced by a native/compatible engine (no such engine is accepted yet) |
| `COMPATIBLE_RENDERED` | produced by a compatible engine (no such engine is accepted yet) |
| `STRUCTURAL_RENDERED` | the source slide's own layout and styling reproduced structurally — the **default** (V0-019 v5); a component that cannot be reproduced is drawn in the platform look in place and warned about |
| `THEMED_RENDERED` | the content re-laid out in the platform theme (the author's grouping kept, the look re-authored) — opt-in |
| `DEGRADED_RENDERED` | renderable, but a human check of meaning is required |

`THEMED_RENDERED` is deliberately **not** on the fidelity-to-source ladder: nothing is claimed about the original appearance, so consumers must not read it as "better" or "worse" than `STRUCTURAL_RENDERED`. It is still an explicit, non-native classification, never a native render. Its content-completeness alarm is `TEXT_OVERFLOW:<scene>`: the scene's content does not fit the page even at the smallest readable type scale. The content is still drawn in full (never truncated) and the scene is degraded for review; the platform omits its own page number on such a scene so nothing is painted over the spill.

`STRUCTURAL_RENDERED` is the default because it reproduces the author's own slide. Its incompleteness alarms are component-scoped and are **warnings, not degradations**: `FONT_SUBSTITUTED:<family>` (the run is drawn in the platform's type stack, in its original frame), `UNSUPPORTED_OBJECT:<kind>` (a chart/SmartArt is drawn as a platform panel, in place), `UNSUPPORTED_MEDIA:`/`MEDIA_BUDGET_EXCEEDED:`/`MEDIA_UNAVAILABLE:` (a picture that cannot be inlined is drawn as a platform panel, in place). The scene is still publishable without a human accepting a "degradation" that is not visible in the output; `DEGRADED_RENDERED` stays reserved for a scene that genuinely cannot be drawn.

Instructional animations become visibility/semantic steps; decorative effects may be dropped. Video becomes timestamped ASR, scene-change frames, OCR, visual events, and segments that runtime can play/pause/resume exactly.

## Locked Decisions Implemented

- `DEC-CONTENT-006`
- `DEC-CONTENT-007`
