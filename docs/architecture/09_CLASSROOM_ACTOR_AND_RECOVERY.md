# Classroom Actor and Recovery

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Specify ownership, fencing, snapshots, replay, and reconnect.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Commands for a class are serialized by `class_id`. Ownership acquisition increments actor epoch. State version increments per accepted transition. Downstream tokens/effects carry epoch and deterministic IDs.

Snapshot contains all orthogonal state regions, versions, lesson/scene/step, queue/floor, timeline checkpoint, pending effects, epoch/version/sequence, schema version, and checksum. Recovery restores, replays, reconciles, revokes stale floor, and resyncs clients using snapshot plus deltas.

## Locked Decisions Implemented

- `DEC-RUNTIME-001`
- `DEC-RUNTIME-004`
- `DEC-RUNTIME-007`
- `DEC-DATA-003`
- `DEC-DATA-004`
