# Content and AI Evaluation

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define regression corpora and quality metrics.

## Dependencies

- `docs/architecture/04_CONTENT_COMPILER.md`
- `docs/architecture/14_LLM_RAG_AND_AI_SAFETY.md`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Corpus covers Vietnamese/custom fonts, basic slides, groups, tables, charts, SmartArt, equations, notes, reveal semantics, media, scans, screen recordings. Measure text/reading-order/object-bounds/render similarity/font issues/reveal accuracy/review seconds. RAG set measures evidence recall/citation correctness/groundedness/cross-version zero. STT set measures Vietnamese WER/final latency/VAD errors. Voice measures TTFA/RTF/intelligibility/marker drift/cancel latency.

## Requirement Trace

- `DEC-CONTENT-006`
- `DEC-CONTENT-007`
- `DEC-DATA-005`
