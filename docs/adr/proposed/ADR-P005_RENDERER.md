# Adr-P005 Renderer

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Document a proposed technology decision without changing canonical architecture.

## Dependencies

- `governance/DECISION_LEDGER.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Status

PROPOSED

## Decision to make

Decide native PowerPoint rendering licensing/worker topology and compatible fallback based on fidelity corpus.

## Relationship to the default render mode (V0-019)

The platform's default fallback render **re-lays the slide's content out as one readable column in a platform-controlled theme** (`THEMED_RENDERED`) rather than reproducing the source slide's own layout and styling: *placement is the platform's and content is the author's*. This is a *rendering-mode* choice expressed behind the `DocumentRenderer` interface; it does **not** accept a renderer technology and does not resolve this proposal. Concretely:

- Themed mode needs no native or compatible engine: its inputs are the Content IR and the compiler-injected picture bytes (`DEC-CONTENT-001`), so it can ship while this ADR is PROPOSED.
- Placement is produced by one measuring pass over a cursor, so two blocks cannot overlap by construction — the failure that motivated the change was that reproducing the author's geometry on the platform's typeface collided (the source deck's own frames overlap). The platform supplies the typeface, the type scale, the palette and the chrome; the source's sizes only select one of three theme rows. Its gate is therefore content completeness (`TEXT_OVERFLOW:<scene>`), not visual similarity to the source. A native/compatible engine would additionally supply the `NATIVE_RENDERED`/`COMPATIBLE_RENDERED` classifications this proposal is about, so accepting this ADR later remains meaningful and additive.
- The faithful structural mode (`STRUCTURAL_RENDERED`) is retained as an explicit mode and remains the closest available reproduction of the source look.

## Required evidence

Prototype benchmark, security/privacy impact, operational complexity, cost, migration/rollback, compatibility with LOCKED decisions, and owner approval. Until accepted, provider-neutral interfaces and mocks are used.
