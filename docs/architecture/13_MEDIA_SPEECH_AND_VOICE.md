# Media, Speech, and Voice

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define SFU topology, STT/TTS lifecycles, floor media, and voice governance.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

One class has one SFU room and shared teacher audio publisher. Students subscribe; floor holder temporarily publishes one audio track. TURN and quality telemetry support difficult networks.

STT has reservation/start/partial/final/cancel/release; partial is ephemeral. TTS has capacity reservation, marker plan, streaming, generation cancellation, and fallback. Authorized cloned voice records consent/scope/expiry/revocation/deletion/audit; neutral voice is fallback.

On media node failure stop grants, revoke floor, reconnect, republish, restore snapshot, and resume at segment boundary.

## Locked Decisions Implemented

- `DEC-TURN-005`
- `DEC-TURN-006`
- `DEC-TURN-008`
- `DEC-DEPLOY-002`
