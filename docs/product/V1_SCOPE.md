# V1 Scope

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Lock the controlled realtime group interaction slice.

## Dependencies

- `docs/architecture/09_CLASSROOM_ACTOR_AND_RECOVERY.md`
- `docs/architecture/11_RAISE_HAND_AND_TURN_CONTROL.md`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Ordered commands, actor epoch/version, snapshot/replay, SFU teacher track, Raise Hand, one floor, STT reservation, audio cancel ACK, final transcript, pinned RAG, dynamic answer, checkpoint resume, moderator, typed fallback, load/chaos/security/accessibility gates. Exclude free multi-speaker discussion and 500-class commitments.

## Requirement Trace

- `DEC-RUNTIME-001`
- `DEC-TURN-001`
- `DEC-TURN-006`
- `DEC-TURN-007`
- `DEC-DATA-004`
