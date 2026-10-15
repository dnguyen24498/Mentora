# Outbox, Snapshot, and Retention

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Specify recovery persistence and data lifecycle.

## Dependencies

- `docs/architecture/16_DATA_STORAGE_AND_EVENTS.md`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Outbox delivers at least once, consumers deduplicate event ID. Snapshot records schema/checksum/epoch/state/event sequence/version tuple/full state/pending effects. Restore validates all fields before replay. Retention is independently configured for raw audio, transcript, questions, analytics, events, audit, recordings, source, voice assets, and backups. Raw student audio defaults off.

## Requirement Trace

- `DEC-DATA-004`
- `DEC-TURN-005`
