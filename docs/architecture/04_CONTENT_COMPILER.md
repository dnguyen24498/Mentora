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

- **`themed` (default)** keeps the author's layout (every object is drawn where and at the size the source put it) and re-styles it in a platform-controlled theme: typeface, palette, and slide chrome are the platform's, not the source deck's. Its fidelity is `THEMED_RENDERED` — a re-styling, **not** a rank on the fidelity-to-source ladder — and the gate is re-scoped from visual fidelity to *content completeness*: nothing is re-selected, re-ordered, or clipped (an `a:noAutofit` text frame spills exactly as PowerPoint spills it), `TEXT_OVERFLOW:` is reported per object rather than losing lines in silence, and the theme owns its typefaces so an unavailable source font cannot degrade a scene. Source colours are mapped onto the theme palette *by role*, so a light-on-dark pair stays light-on-dark.
- **`faithful`** reproduces the source slide's own geometry and styling and reports `STRUCTURAL_RENDERED`.

An object that cannot be re-styled (a chart, SmartArt) degrades the scene (`UNSUPPORTED_OBJECT:`) and requires review rather than being silently flattened. The renderer never reads the source package: it receives the Content IR and the picture bytes the compiler injects (`DEC-CONTENT-001`).

## Vision

Invoked only for scans, diagrams, complex charts, SmartArt fallback, or meaning carried by position/color/arrows. Every invocation records reason, model/prompt versions, source refs, confidence, and review state.

## Security/reproducibility

Sandbox untrusted files, never execute macros/scripts/OLE, bound resources and archive expansion. Deterministic cache key uses source checksum, compiler version, renderer identity, and config hash.

## Locked Decisions Implemented

- `DEC-CONTENT-001`
- `DEC-CONTENT-002`
- `DEC-CONTENT-006`
- `DEC-CONTENT-009`
