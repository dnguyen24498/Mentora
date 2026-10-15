# WebSocket Protocol

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define reliable classroom control communication.

## Dependencies

- `docs/architecture/16_API_WEBSOCKET_COMMAND_AND_EVENT_CONTRACTS.md`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Client obtains short-lived bootstrap token, sends hello with supported schemas and last contiguous sequence. Server returns epoch/current sequence and snapshot/delta decision. Client ACKs highest contiguous sequence. Duplicate IDs are ignored; gaps freeze unsafe controls and request resync. Commands have stable IDs. Server distinguishes accepted-for-ordering from terminal result. Priority traffic includes revoke and audio cancel ACK. Reconnect discards floor token.

## Requirement Trace

- `DEC-RUNTIME-003`
- `DEC-RUNTIME-004`
