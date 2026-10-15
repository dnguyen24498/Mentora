# Raise Hand and Turn Control

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define control-first, audio-on-demand interaction.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Group microphones remain unpublished. Raise Hand is a control command. Queue uses configurable fairness. Before floor: reserve STT, verify connection, reach safe marker, checkpoint, cancel teacher audio, await ACK or safe timeout, mint fenced short-lived floor token.

On publication ACK, enter SPEAKING and start STT. Finish/VAD/timeout/revoke/disconnect transitions exactly once to finalization; stop STT, unpublish, revoke, release capacity, produce final transcript. Typed question remains available.

## Locked Decisions Implemented

- `DEC-TURN-001`
- `DEC-TURN-002`
- `DEC-TURN-003`
- `DEC-TURN-004`
- `DEC-TURN-005`
- `DEC-TURN-006`
- `DEC-TURN-007`
- `DEC-TURN-008`
- `DEC-TURN-009`
