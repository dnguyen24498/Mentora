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

The platform's default fallback render **reproduces the source slide's own layout and styling** (`STRUCTURAL_RENDERED`) and draws any component it cannot reproduce in the platform's own look, **in place**. This is a *rendering-mode* choice expressed behind the `DocumentRenderer` interface; it does **not** accept a renderer technology and does not resolve this proposal. Concretely:

- Neither mode needs a native or compatible engine: both take the Content IR and the compiler-injected picture bytes (`DEC-CONTENT-001`) as input, so they can ship while this ADR is PROPOSED.
- The default keeps the author's layout because that is what an author expects to see, and the product rule is *"same layout as the author's deck; where a component cannot be reproduced, draw it in the platform's default look, in place"*. A component the renderer cannot reproduce is therefore never dropped and never silently flattened: an unavailable source font is substituted with the platform's type stack (deterministically, so the client's fonts cannot change the asset), and a chart/SmartArt or an un-inlinable picture is drawn as a flat platform panel in its original frame. Each is a warning, not a degradation.
- Keeping the author's geometry means keeping the author's geometry: where a source deck's own frames overlap, the overlap is reproduced, exactly as PowerPoint shows it. To stop a *substituted* typeface from spilling text over a neighbouring block, a frame whose font was substituted is shrunk to stay inside the author's frame.
- The opt-in `themed` mode is the alternative: it recovers the author's **grouping** with a binary widest-gap XY-cut over the source boxes (so an icon stays beside its label and a card keeps its parts) and then re-authors the look — placement is produced by one measuring pass over a cursor, so two blocks cannot overlap by construction. Its gate is content completeness (`TEXT_OVERFLOW:<scene>`), not visual similarity. A native/compatible engine would additionally supply the `NATIVE_RENDERED`/`COMPATIBLE_RENDERED` classifications this proposal is about, so accepting this ADR later remains meaningful and additive.
- Both modes estimate text metrics from a font-free advance table rather than measuring them, so a substituted typeface can wrap a line a word earlier than PowerPoint would. That, not the mode choice, is the limit a native/compatible engine would remove.

## Required evidence

Prototype benchmark, security/privacy impact, operational complexity, cost, migration/rollback, compatibility with LOCKED decisions, and owner approval. Until accepted, provider-neutral interfaces and mocks are used.
