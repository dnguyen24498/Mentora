# Content Compiler Architecture

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Specify secure deterministic compilation and selective enrichment.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Pipeline

Validate/scan/store -> structural extraction -> rendering router -> media processing -> reveal semantics -> Content IR -> baseline builder -> selective AI enrichment -> validation.

## Rendering

Record engine/version/fonts/warnings/provenance and classify native-compatible-structural-degraded-failed. Failed blocks publication; degraded meaning requires review.

Two local render modes sit behind the renderer interface while the production renderer technology is `OPEN`:

- **`themed` (default)** **re-lays the content out**: *placement is the platform's and content is the author's*. The extracted objects are folded into flow blocks (a list of paragraphs, a table, a row of pictures) and placed in **one readable column in reading order** by a single measuring pass over a cursor — position and measurement are the same computation, so two blocks cannot overlap by construction — behind a hoisted heading (kicker/title/subtitle over one hairline rule), with the page number in a reserved bottom strip the flow may not enter. The look is the platform's throughout: its type stack, its type scale, its palette; no source typeface, colour, fill or geometry is reproduced. Its fidelity is `THEMED_RENDERED` — a re-layout, **not** a rank on the fidelity-to-source ladder — and the gate is *content completeness*, not visual fidelity: nothing is re-selected, re-ordered or dropped. The source's own sizes select one of three theme rows (`lead`/`body`/`caption`), so a 40 pt statistic still reads as a statement beside a 12 pt note, and its bold/italic runs survive. Content that cannot be fitted even at the smallest readable type scale (`flow.LADDER`, then a continuous shrink to `theme.min_scale`) is still drawn, flagged `TEXT_OVERFLOW:<scene>`, degraded for review, and the page number is omitted so nothing is covered. Text metrics are estimated from a font-free advance table (`textmetrics.py`), so a line may break a word early — it can never collide with its neighbour.
- **`faithful`** reproduces the source slide's own geometry and styling and reports `STRUCTURAL_RENDERED`.

An object that cannot be redrawn from the IR (a chart, SmartArt) becomes a labelled panel, degrades the scene (`UNSUPPORTED_OBJECT:`) and requires review rather than being silently flattened. The renderer never reads the source package: it receives the Content IR and the picture bytes the compiler injects (`DEC-CONTENT-001`).

## Vision

Invoked only for scans, diagrams, complex charts, SmartArt fallback, or meaning carried by position/color/arrows. Every invocation records reason, model/prompt versions, source refs, confidence, and review state.

## Security/reproducibility

Sandbox untrusted files, never execute macros/scripts/OLE, bound resources and archive expansion. Deterministic cache key uses source checksum, compiler version, renderer identity, and config hash.

## Locked Decisions Implemented

- `DEC-CONTENT-001`
- `DEC-CONTENT-002`
- `DEC-CONTENT-006`
- `DEC-CONTENT-009`
