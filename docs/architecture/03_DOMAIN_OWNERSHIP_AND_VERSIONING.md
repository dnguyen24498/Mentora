# Domain, Ownership, and Versioning

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define canonical models and authoritative owners.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Aggregates

Institution, Course/CourseVersion/SourceArtifact, ContentPackage/CTF/TeachingGraph/LessonPlan/KnowledgeIndex, Class/RuntimeSessionPlan/ClassroomSession, Student/Enrollment/Progress, VoiceAuthorization.

## Ownership

Compiler owns Content IR; Publication Service owns immutable package relationships; Classroom Actor owns active state; Teacher Orchestrator owns pedagogical proposals; PostgreSQL-equivalent owns durable records; event log owns ordered history; Redis is projection/cache; search is rebuildable.

## Runtime tuple

Course, CTF, content package, lesson, optional teaching graph, assessment, knowledge index, policy, model-routing configuration, and home region are explicit versions. `latest` is forbidden.

## Locked Decisions Implemented

- `DEC-CONTENT-004`
- `DEC-CONTENT-005`
- `DEC-RUNTIME-001`
- `DEC-RUNTIME-002`
- `DEC-DATA-001`
- `DEC-DATA-002`
